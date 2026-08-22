using Meta.XR;
using Meta.XR.MRUtilityKit;
using System.Collections.Generic;
using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using System.Threading.Tasks;
using System.Text;
using UnityEngine.Networking;
using UnityEngine.Android;



public class AppFlow : MonoBehaviour
{
    [SerializeField] private TMP_Text infoText;
    [SerializeField] private Button okButton;
    [SerializeField] private PassthroughCameraAccess cameraAccess;

    [Header("Auto-capture")]
    [SerializeField] private float segmentSize = 2.2f;       // ~5m² per cell
    [SerializeField] private float minCaptureDepth = 3.0f;   // meters
    [SerializeField] private float checkInterval = 0.25f;    // how often the depth probe is refreshed

    [Header("Aiming")]
    [Tooltip("Half-angle of the aim ring. The ring's edge sits exactly this far off the target heading.")]
    [SerializeField] private float aimTolerance = 20f;
    [Tooltip("Seconds the aim must be held. The shot is taken halfway through the fill.")]
    [SerializeField] private float aimHoldTime = 1.4f;
    [Tooltip("Head turn rate in deg/s above which the shot is held back, so a spin cannot trigger it.")]
    [SerializeField] private float maxAimTurnRate = 45f;
    [Tooltip("How far in front of the user the aim ring floats.")]
    [SerializeField] private float ringDistance = 2f;

    [Header("Floor filtering")]
    [Tooltip("Horizontal clearance kept around furniture. A spot this close to a volume counts as blocked.")]
    [SerializeField] private float personRadius = 0.25f;
    [Tooltip("A cell needs at least this fraction of standable floor to be worth visiting.")]
    [SerializeField] private float minFreeFloorRatio = 0.20f;
    [Tooltip("Volumes whose underside sits higher than this above the floor are walked under, not around (wall screens, high shelves).")]
    [SerializeField] private float floorObstacleMaxHeight = 0.30f;
    [Tooltip("Samples per axis when measuring how much of a cell is standable floor.")]
    [SerializeField] private int floorSamplesPerAxis = 5;

    [Header("Backend")]
    [SerializeField] private string apiUrl = "https://bernhackt26.kirchenfeldrobotics.ch";  // FastAPI url

    [Header("Input hardening")]
    [SerializeField] private float okClickDebounce = 0.30f;  // ignore repeat OK clicks inside this window

    [Header("UI placement")]
    [SerializeField] private Transform uiPanel;                  // defaults to the canvas' parent
    [SerializeField] private float panelDistance = 1.2f;         // metres in front of the user
    [SerializeField] private float panelHeightOffset = -0.1f;    // relative to eye height
    [SerializeField] private float panelFollowAngle = 35f;       // start following past this angle
    [SerializeField] private float panelFollowSpeed = 2.5f;

    [Header("Diagnostics")]
    [SerializeField] private bool logUiDiagnostics = false;      // verbose TMP dump on every state change
    [SerializeField] private bool logCaptureDiagnostics = true;  // why did this cell not capture?

    private enum State { Permissions, Checking, ConfirmReady, ConfirmScan, Scanning, Capturing, Complete }
    private State state;

    private Camera headCam;
    private Transform panelRoot;
    private bool panelFollowing;
    private string captureHint = "";

    private class CaptureCell
    {
        public int gridX, gridZ;
        public Vector3 worldCenter;   // geometric centre of the grid cell; defines its extents
        public Vector3 standPoint;    // a spot inside the cell that is actually standable floor
        public float freeRatio;       // fraction of the cell that is standable floor
        public bool captured;

        public Vector3 aimDirection;  // horizontal heading the user must face here
        public float requiredDepth;   // normally minCaptureDepth, lowered for enclosed spots
        public bool aimRelaxed;       // true when nothing here reaches minCaptureDepth
        public Vector3 aimAnchor;     // head position the heading was solved from
        public bool aimSolved;
    }
    private List<CaptureCell> cells = new List<CaptureCell>();
    private float captureGraceUntil;
    private int capturedCount;

    private Vector3 roomCentroid;
    private float aimProgress;
    private float confirmTimer;
    private Vector3 confirmAimDir;
    private Vector3 lastHeadForward;
    private float headTurnRate;
    private float cachedDepth;
    private float nextDepthTime;

    private Canvas ringCanvas;
    private RectTransform ringBaseRect, ringFillRect;
    private Image ringBaseImg, ringFillImg;
    private bool ringVisible;

    static readonly Color RingIdle = new Color(1f, 1f, 1f, 0.30f);
    static readonly Color RingArmed = new Color(0.35f, 1f, 0.55f, 0.55f);
    static readonly Color RingBlocked = new Color(1f, 0.72f, 0.20f, 0.60f);
    static readonly Color RingConfirm = new Color(0.35f, 1f, 0.55f, 0.90f);
    static readonly Color FillArmed = new Color(0.35f, 1f, 0.55f, 0.95f);

    private int okClickCount;
    private int lastOkClickFrame = -1;
    private float lastOkClickTime = -999f;

    private string lastCaptureDiag = "";
    private float nextDiagTime;

    private List<byte[]> capturedFrames = new List<byte[]>();

    [System.Serializable]
    private class AnchorData
    {
        public string label;
        public float[] position;
        public float[] rotation;
        public float[] size;   // may be null
    }

    [System.Serializable]
    private class RoomData
    {
        public AnchorData[] anchors;
    }

    [System.Serializable]
    private class Payload
    {
        public RoomData room;
        public string[] captures;  // base64-encoded JPGs
    }

    void Awake()
    {
        Application.SetStackTraceLogType(LogType.Log, StackTraceLogType.None);
        headCam = ResolveHeadCamera();
    }

    // The scene tags BOTH LeftEyeAnchor and CenterEyeAnchor as MainCamera, which makes
    // Camera.main ambiguous (and LeftEyeAnchor is the wrong pose). Resolve explicitly.
    Camera ResolveHeadCamera()
    {
        OVRCameraRig rig = FindAnyObjectByType<OVRCameraRig>();
        if (rig != null && rig.centerEyeAnchor != null)
        {
            Camera c = rig.centerEyeAnchor.GetComponent<Camera>();
            if (c != null) { Debug.Log("[AppFlow] Head camera = OVRCameraRig.centerEyeAnchor"); return c; }
        }
        foreach (Camera c in Camera.allCameras)
            if (c.name == "CenterEyeAnchor") { Debug.Log("[AppFlow] Head camera = CenterEyeAnchor (by name)"); return c; }

        Debug.LogWarning("[AppFlow] Falling back to Camera.main - centre-eye camera not found.");
        return Camera.main;
    }

    // The scene applies the 0.001 world-space scale on the Canvas AND again on its
    // children, so everything below it renders at 1e-6 - i.e. invisible. Anything
    // inside an already-scaled world-space canvas must sit at scale 1.
    void NormalizeUi()
    {
        if (infoText == null) { Debug.LogError("[AppFlow] infoText is not assigned."); return; }

        Canvas canvas = infoText.canvas != null ? infoText.canvas : infoText.GetComponentInParent<Canvas>();
        if (canvas == null) { Debug.LogError("[AppFlow] infoText is not under a Canvas."); return; }

        panelRoot = uiPanel != null ? uiPanel
                  : (canvas.transform.parent != null ? canvas.transform.parent : canvas.transform);

        // Direct children only. The backplate prefab hides a grandchild ('UIBackplate')
        // that is both 0.001-scaled AND sized 800 x -1900; rescaling that one would turn
        // an invisible speck into a large misplaced quad, so it is deliberately left alone.
        foreach (Transform child in canvas.transform)
        {
            if (child is RectTransform rt)
            {
                Vector3 s = rt.localScale;
                if (s.x > 0f && s.x < 0.01f)
                {
                    Debug.LogWarning($"[AppFlow][ui] '{rt.name}' had localScale {s} inside a world-space canvas -> reset to 1");
                    rt.localScale = Vector3.one;
                }
            }
            else if (child.localPosition.sqrMagnitude > 1f)
            {
                // A plain Transform directly under a Canvas is abnormal; the backplate root
                // sits ~2.3 m off to the side because of a stray local position.
                Debug.LogWarning($"[AppFlow][ui] '{child.name}' at localPosition {child.localPosition} -> recentred");
                child.localPosition = Vector3.zero;
            }
        }

        // Readable against arbitrary passthrough backgrounds.
        infoText.color = Color.white;
        infoText.outlineColor = new Color32(0, 0, 0, 255);
        infoText.outlineWidth = 0.2f;
        infoText.enableAutoSizing = false;
    }

    async void Start()
    {
        NormalizeUi();
        okButton.onClick.AddListener(OnOkClicked);

        Debug.Log($"[AppFlow][diag] Start() on '{gameObject.name}' " +
                  $"appFlowId={GetEntityId()} " +
                  $"appFlowsInScene={FindObjectsByType<AppFlow>(FindObjectsInactive.Include).Length} " +
                  $"okButton='{okButton.name}' okButtonId={okButton.GetEntityId()} " +
                  $"inspectorListeners={okButton.onClick.GetPersistentEventCount()}");

        MRUK.Instance.RegisterSceneLoadedCallback(OnSceneLoaded);

        // Both of these are runtime-dangerous permissions on Horizon OS. Nothing else in
        // this project requests them: OVRManager has requestScenePermissionOnStartup and
        // requestPassthroughCameraAccessPermissionOnStartup both off, MRUK only asks when
        // SceneSettings.LoadSceneOnStartup is on (it is off), and PassthroughCameraAccess
        // only *waits* for the grant. Without this block the room never loads and the
        // camera never starts.
        if (!await EnsurePermission(OVRPermissionsRequester.ScenePermission, "Scene / spatial data"))
        {
            SetState(State.Complete,
                "⚠ Scene permission denied.\nThe app cannot read your room.\nGrant it in Settings → Apps and restart.",
                showButton: false);
            return;
        }
        if (!await EnsurePermission(OVRPermissionsRequester.PassthroughCameraAccessPermission, "Headset camera"))
        {
            SetState(State.Complete,
                "⚠ Camera permission denied.\nThe app cannot capture images.\nGrant it in Settings → Apps and restart.",
                showButton: false);
            return;
        }

        SetState(State.Checking, "Checking for existing room scan...", showButton: false);

        // Try loading WITHOUT triggering setup
        var result = await MRUK.Instance.LoadSceneFromDevice(requestSceneCaptureIfNoDataFound: false);
        Debug.Log($"[AppFlow] Initial load result: {result}");

        var room = MRUK.Instance.GetCurrentRoom();
        bool hasRoom = room != null && room.Anchors.Count > 0;
        Debug.Log($"[AppFlow] hasRoom={hasRoom}, anchor count={room?.Anchors.Count ?? 0}");

        if (hasRoom)
        {
            SetState(State.ConfirmReady,
                "✓ Scanned room detected.\nProcessing data...\n\nPress OK to continue.");
        }
        else
        {
            SetState(State.ConfirmScan,
                "⚠ No room scan detected.\nPress OK to start scanning your room.");
        }
    }

    // Requests one Android permission and waits for the user's answer.
    // Returns true if granted. No-ops (returns true) off-device.
    async Task<bool> EnsurePermission(string permission, string friendlyName)
    {
        if (Permission.HasUserAuthorizedPermission(permission))
        {
            Debug.Log($"[AppFlow] Permission already granted: {permission}");
            return true;
        }

        SetState(State.Permissions,
            $"Requesting permission:\n<b>{friendlyName}</b>\n\nPlease accept the system dialog.",
            showButton: false);
        Debug.Log($"[AppFlow] Requesting permission: {permission}");

        bool answered = false, granted = false;
        var cb = new PermissionCallbacks();
        cb.PermissionGranted += _ => { granted = true; answered = true; };
        cb.PermissionDenied += _ => { granted = false; answered = true; };
        Permission.RequestUserPermission(permission, cb);

        // If a permission dialog is already on screen this request silently fails and the
        // callbacks never fire, so poll as well (same workaround MRUK uses internally).
        float deadline = Time.unscaledTime + 180f;
        while (!answered && Time.unscaledTime < deadline)
        {
            if (Permission.HasUserAuthorizedPermission(permission)) { granted = true; break; }
            await Task.Yield();
        }

        if (!granted) granted = Permission.HasUserAuthorizedPermission(permission);
        Debug.Log($"[AppFlow] Permission {permission} granted={granted}");
        return granted;
    }

    void OnOkClicked()
    {
        okClickCount++;
        Debug.Log($"[AppFlow][diag] OnOkClicked #{okClickCount} frame={Time.frameCount} " +
                  $"t={Time.unscaledTime:F4} state={state} appFlowId={GetEntityId()} " +
                  $"prevFrame={lastOkClickFrame} prevT={lastOkClickTime:F4}");

        if (Time.frameCount == lastOkClickFrame ||
            Time.unscaledTime - lastOkClickTime < okClickDebounce)
        {
            Debug.LogWarning($"[AppFlow] Ignored duplicate OK click #{okClickCount} " +
                             $"(same frame: {Time.frameCount == lastOkClickFrame}, " +
                             $"dt={Time.unscaledTime - lastOkClickTime:F4}s)");
            return;
        }
        lastOkClickFrame = Time.frameCount;
        lastOkClickTime = Time.unscaledTime;

        Debug.Log($"[AppFlow] OK clicked in state {state}");
        if (state == State.ConfirmReady) EnterCaptureMode();
        else if (state == State.ConfirmScan) StartScan();
    }

    async void StartScan()
    {
        SetState(State.Scanning,
            "Launching Space Setup...\nFollow the on-screen instructions.\nApp will resume when done.",
            showButton: false);

        var result = await MRUK.Instance.LoadSceneFromDevice(requestSceneCaptureIfNoDataFound: true);
        Debug.Log($"[AppFlow] Scan result: {result}");

        var room = MRUK.Instance.GetCurrentRoom();
        if (room != null && room.Anchors.Count > 0)
        {
            EnterCaptureMode();
        }
        else
        {
            SetState(State.ConfirmScan,
                $"Scan didn't complete ({result}).\nPress OK to try again.");
        }
    }

    void OnSceneLoaded()
    {
        var room = MRUK.Instance.GetCurrentRoom();
        Debug.Log($"[AppFlow] Scene loaded callback. Anchors: {room?.Anchors.Count ?? 0}");
    }

    // Capture

    void EnterCaptureMode()
    {
        SegmentRoom();
        if (cells.Count == 0)
        {
            SetState(State.Complete,
                "<b>No standable floor found</b>\nThis room scan has no open floor large enough to stand in.\nRe-scan the room, or lower Segment Size.",
                showButton: false);
            return;
        }
        capturedCount = 0;

        // Every cell aims at the centroid of all the stand points, i.e. the open middle of
        // the room. That makes the shots fan inwards and cover the place between them,
        // instead of all pointing the same way and photographing one wall three times.
        roomCentroid = Vector3.zero;
        foreach (var c in cells) roomCentroid += c.standPoint;
        roomCentroid /= cells.Count;

        aimProgress = 0f;
        confirmTimer = 0f;
        headTurnRate = 0f;
        lastHeadForward = Vector3.zero;
        foreach (var c in cells) c.aimSolved = false;

        captureGraceUntil = Time.time + 1.0f;  // 1s grace period so user can look around first
        captureHint = "Walk to a spot, then face the ring.";
        SetState(State.Capturing, BuildCaptureText(), showButton: false);
        Debug.Log($"[AppFlow] Starting auto-capture. {cells.Count} segments to cover. " +
                  $"Aim centroid {roomCentroid}, ring {aimTolerance:F0}deg, hold {aimHoldTime:F1}s.");
    }

    void Update()
    {
        UpdatePanelPlacement();

        if (state != State.Capturing) { ShowRing(false); return; }

        if (headCam == null) headCam = ResolveHeadCamera();
        if (headCam == null)
        {
            ShowRing(false);
            CaptureDiag("No head camera found - cannot tell which cell you are in");
            return;
        }

        // Aiming runs every frame, not on checkInterval. The ring animates, and a turn rate
        // sampled at 4 Hz cannot tell a held pose from a head swinging through one.
        Transform head = headCam.transform;
        TrackHeadTurn(head);

        // Play out the back half of the ring after the shutter, so the user sees the shot
        // land instead of the ring simply vanishing.
        if (confirmTimer > 0f)
        {
            confirmTimer -= Time.deltaTime;
            float t = 1f - Mathf.Clamp01(confirmTimer / Mathf.Max(0.05f, aimHoldTime * 0.5f));
            DrawRing(head, confirmAimDir, 0.5f + 0.5f * t, RingConfirm, FillArmed);
            if (confirmTimer <= 0f) { aimProgress = 0f; ShowRing(false); }
            return;
        }

        if (Time.time < captureGraceUntil) { ShowRing(false); return; }

        if (cameraAccess == null)
        {
            ShowRing(false);
            CaptureDiag("PassthroughCameraAccess is not assigned in the Inspector");
            return;
        }
        if (!cameraAccess.IsPlaying)
        {
            ShowRing(false);
            CaptureDiag("Waiting for the passthrough camera to start...");
            return;
        }

        CaptureCell cell = FindCellForPosition(head.position);
        if (cell == null)
        {
            ShowRing(false); aimProgress = 0f;
            CaptureDiag($"Move into an uncaptured area. {NearestCellHint(head.position)}");
            return;
        }
        if (cell.captured)
        {
            ShowRing(false); aimProgress = 0f;
            CaptureDiag($"This spot is done. {NearestCellHint(head.position)}");
            return;
        }

        UpdateAiming(head, cell);
    }

    // The old loop fired the shutter the instant one sample passed, so a head still turning
    // sent the camera whatever it swung onto next, and nothing said which way to look, so
    // every cell could be shot in the same direction. One mechanism fixes both: a fixed
    // target heading (the ring) that has to be held still for a moment before the shutter.
    void UpdateAiming(Transform head, CaptureCell cell)
    {
        Vector3 gaze = Flat(head.forward);
        if (gaze == Vector3.zero) return;

        // Re-solve only while the ring is empty. Moving the target under a half-filled ring
        // is worse than letting it go slightly stale.
        if (!cell.aimSolved ||
            (aimProgress <= 0f && (head.position - cell.aimAnchor).sqrMagnitude > 0.25f))
            SolveAim(cell, head.position);

        if (Time.time >= nextDepthTime)
        {
            nextDepthTime = Time.time + Mathf.Max(0.02f, checkInterval);
            cachedDepth = MeasureDepthAhead(head.position, head.forward);
        }

        float off = Vector3.Angle(gaze, cell.aimDirection);
        bool onTarget = off <= aimTolerance;
        bool steady = headTurnRate <= maxAimTurnRate;
        bool deep = cachedDepth >= cell.requiredDepth;

        if (onTarget && steady && deep)
        {
            float before = aimProgress;
            aimProgress = Mathf.Min(1f, aimProgress + Time.deltaTime / Mathf.Max(0.2f, aimHoldTime));
            CaptureDiag(cell.aimRelaxed
                ? "Tight spot — taking the best view there is. Hold still."
                : "Hold still...");
            if (before < 0.5f && aimProgress >= 0.5f) TryCapture(cell, head);
        }
        else
        {
            aimProgress = 0f;
            if (!onTarget) CaptureDiag($"Turn to face the ring ({off:F0}° off).");
            else if (!steady) CaptureDiag("Slow down — hold your head still inside the ring.");
            else CaptureDiag($"No open view here — need {cell.requiredDepth:F1} m, you have {cachedDepth:F1} m.");
        }

        Color baseCol = !onTarget ? RingIdle : (deep && steady ? RingArmed : RingBlocked);
        DrawRing(head, cell.aimDirection, aimProgress, baseCol, FillArmed);
    }

    // Runs on the exact frame the ring passes its halfway mark.
    void TryCapture(CaptureCell cell, Transform head)
    {
        // Probe again rather than trust the cached value. This is the frame that matters,
        // and it is the check the old code never made at the moment of the shot.
        float depth = MeasureDepthAhead(head.position, head.forward);
        if (depth < cell.requiredDepth)
        {
            aimProgress = 0f;
            CaptureDiag($"Lost the open view right at the shot ({depth:F1} m). Line the ring up again.");
            return;
        }

        if (!CaptureFrame()) { aimProgress = 0f; return; }

        cell.captured = true;
        capturedCount++;
        confirmAimDir = cell.aimDirection;
        confirmTimer = Mathf.Max(0.15f, aimHoldTime * 0.5f);

        Debug.Log($"[AppFlow] Captured cell ({cell.gridX},{cell.gridZ}) depth={depth:F1}m " +
                  $"aim-error={Vector3.Angle(Flat(head.forward), cell.aimDirection):F0}° " +
                  $"turn-rate={headTurnRate:F0}°/s -> {capturedCount}/{cells.Count}");

        if (capturedCount >= cells.Count)
        {
            SetState(State.Complete,
                $"<b>✓ Capture complete</b>\n{ProgressBar(cells.Count, cells.Count)}\n{cells.Count} images — uploading...",
                showButton: false);
            _ = SendDataSafe();
        }
        else
        {
            captureHint = "Got it. Move to the next area.";
            infoText.text = BuildCaptureText();
        }
    }

    // Which way should the user face from here?
    //   1. Straight at the centroid of every stand point. That is the open middle of the
    //      room, so it is both the most informative shot and usually the deepest.
    //   2. If something blocks that, the nearest heading to it that does clear the bar, so
    //      the shot stays as close to "into the room" as it can.
    //   3. If nothing in a full circle clears it, the deepest heading there is, with the bar
    //      lowered to match. Dropping the cell instead would leave a hole in the coverage
    //      and could strand the run one capture short of ever finishing.
    void SolveAim(CaptureCell cell, Vector3 from)
    {
        cell.aimAnchor = from;
        cell.aimSolved = true;

        // Standing on the centroid makes "face the centroid" meaningless.
        if ((roomCentroid - from).sqrMagnitude <= 1f)
        {
            cell.aimDirection = MostNovelDirection(cell, from, out float dm);
            cell.aimRelaxed = dm < minCaptureDepth;
            cell.requiredDepth = cell.aimRelaxed ? Mathf.Max(0.5f, dm * 0.9f) : minCaptureDepth;
            LogAim(cell, dm, "centre of the room, least-covered heading");
            return;
        }

        Vector3 preferred = Flat(roomCentroid - from);
        float depth = MeasureDepthAhead(from, preferred);
        if (depth >= minCaptureDepth)
        {
            cell.aimDirection = preferred;
            cell.requiredDepth = minCaptureDepth;
            cell.aimRelaxed = false;
            LogAim(cell, depth, "at the centroid");
            return;
        }

        Vector3 best = preferred;
        float bestDepth = depth;
        for (int stepIdx = 1; stepIdx <= 12; stepIdx++)
        {
            for (int sign = -1; sign <= 1; sign += 2)
            {
                Vector3 dir = Quaternion.AngleAxis(stepIdx * 15f * sign, Vector3.up) * preferred;
                float d = MeasureDepthAhead(from, dir);
                if (d > bestDepth) { bestDepth = d; best = dir; }
                if (d >= minCaptureDepth)
                {
                    cell.aimDirection = dir;
                    cell.requiredDepth = minCaptureDepth;
                    cell.aimRelaxed = false;
                    LogAim(cell, d, $"swung {stepIdx * 15 * sign}° clear of an obstruction");
                    return;
                }
                if (stepIdx == 12) break;   // +/-180 name the same heading
            }
        }

        cell.aimDirection = best;
        cell.requiredDepth = Mathf.Max(0.5f, bestDepth * 0.9f);
        cell.aimRelaxed = true;
        LogAim(cell, bestDepth, "enclosed spot, depth bar lowered");
    }

    // From the middle of the room every heading is equally valid, so just taking the deepest
    // one would point every central cell the same way - the exact redundancy the ring exists
    // to prevent. Take the heading least like the ones already handed out instead.
    Vector3 MostNovelDirection(CaptureCell forCell, Vector3 from, out float depth)
    {
        Vector3 best = Vector3.forward;
        float bestScore = float.MinValue;
        depth = 0f;

        for (int i = 0; i < 24; i++)
        {
            Vector3 dir = Quaternion.AngleAxis(i * 15f, Vector3.up) * Vector3.forward;
            float d = MeasureDepthAhead(from, dir);

            // Skip forCell itself: SolveAim has already flagged it solved, and scoring it
            // against its own stale heading would flip the ring round on every re-solve.
            float novelty = 180f;
            foreach (var c in cells)
                if (c != null && c != forCell && c.aimSolved && c.aimDirection != Vector3.zero)
                    novelty = Mathf.Min(novelty, Vector3.Angle(dir, c.aimDirection));

            // Clearing the depth bar always beats not clearing it; novelty only breaks ties
            // among the headings that do clear it.
            float score = d >= minCaptureDepth ? 1000f + novelty : d * 100f;
            if (score > bestScore) { bestScore = score; best = dir; depth = d; }
        }
        return best;
    }

    void LogAim(CaptureCell cell, float depth, string why)
    {
        Vector3 toCentroid = Flat(roomCentroid - cell.aimAnchor);
        float bearing = toCentroid == Vector3.zero
            ? 0f : Vector3.SignedAngle(toCentroid, cell.aimDirection, Vector3.up);
        Debug.Log($"[AppFlow][aim] cell ({cell.gridX},{cell.gridZ}) heading {cell.aimDirection} " +
                  $"({bearing:F0}° off the centroid, {why}), depth {depth:F1} m, " +
                  $"need {cell.requiredDepth:F1} m{(cell.aimRelaxed ? " [RELAXED]" : "")}");
    }

    void TrackHeadTurn(Transform head)
    {
        Vector3 f = head.forward;
        if (lastHeadForward != Vector3.zero && Time.deltaTime > 1e-5f)
        {
            float instant = Vector3.Angle(lastHeadForward, f) / Time.deltaTime;
            headTurnRate = Mathf.Lerp(headTurnRate, instant, 0.35f);   // ride out single-frame spikes
        }
        lastHeadForward = f;
    }

    static Vector3 Flat(Vector3 v)
    {
        v.y = 0f;
        return v.sqrMagnitude > 1e-6f ? v.normalized : Vector3.zero;
    }

    // The ring is built in code so it needs nothing wired up in the scene. It is a
    // world-space Canvas because uGUI's UI/Default shader is always included in a build,
    // whereas a Shader.Find for anything else can come back null on device.
    void EnsureRing()
    {
        if (ringCanvas != null) return;

        GameObject root = new GameObject("AimRing", typeof(Canvas));
        ringCanvas = root.GetComponent<Canvas>();
        ringCanvas.renderMode = RenderMode.WorldSpace;
        ringCanvas.sortingOrder = 100;
        root.transform.localScale = Vector3.one * 0.001f;   // same mm convention as the info panel

        Sprite sprite = BuildRingSprite(256, 0.80f, 0.94f);
        ringBaseImg = CreateRingImage(root.transform, "Base", sprite, out ringBaseRect);
        ringFillImg = CreateRingImage(root.transform, "Fill", sprite, out ringFillRect);
        ringFillImg.type = Image.Type.Filled;
        ringFillImg.fillMethod = Image.FillMethod.Radial360;
        ringFillImg.fillOrigin = (int)Image.Origin360.Top;
        ringFillImg.fillClockwise = true;
        ringFillImg.fillAmount = 0f;

        root.SetActive(false);
        ringVisible = false;
    }

    static Image CreateRingImage(Transform parent, string name, Sprite s, out RectTransform rect)
    {
        GameObject go = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
        go.transform.SetParent(parent, false);
        rect = (RectTransform)go.transform;
        rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 0.5f);
        rect.anchoredPosition = Vector2.zero;
        Image img = go.GetComponent<Image>();
        img.sprite = s;
        img.raycastTarget = false;
        return img;
    }

    static Sprite BuildRingSprite(int size, float innerFrac, float outerFrac)
    {
        Texture2D tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
        tex.wrapMode = TextureWrapMode.Clamp;

        Color32[] px = new Color32[size * size];
        float c = (size - 1) * 0.5f;
        float inner = innerFrac * c, outer = outerFrac * c;
        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float d = Mathf.Sqrt((x - c) * (x - c) + (y - c) * (y - c));
                // one-pixel feather on both edges so the ring does not crawl at arm's length
                float a = Mathf.Clamp01(Mathf.Min(d - inner, outer - d));
                px[y * size + x] = new Color32(255, 255, 255, (byte)(a * 255f));
            }
        }
        tex.SetPixels32(px);
        tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f));
    }

    void ShowRing(bool show)
    {
        if (!show && ringCanvas == null) { ringVisible = false; return; }
        if (show == ringVisible) return;
        EnsureRing();
        ringCanvas.gameObject.SetActive(show);
        ringVisible = show;
    }

    void DrawRing(Transform head, Vector3 aimDir, float fill, Color baseColor, Color fillColor)
    {
        if (aimDir == Vector3.zero) { ShowRing(false); return; }
        EnsureRing();
        ShowRing(true);
        if (ringCanvas.worldCamera == null) ringCanvas.worldCamera = headCam;

        Vector3 centre = head.position + aimDir * ringDistance;
        ringCanvas.transform.SetPositionAndRotation(centre, Quaternion.LookRotation(aimDir, Vector3.up));

        // The ring is the tolerance cone drawn out: its edge sits exactly aimTolerance
        // degrees off axis, so "inside the ring" and "within tolerance" are the same thing.
        float d = 2f * ringDistance * Mathf.Tan(aimTolerance * Mathf.Deg2Rad) * 1000f;
        ringBaseRect.sizeDelta = ringFillRect.sizeDelta = new Vector2(d, d);

        ringBaseImg.color = baseColor;
        ringFillImg.color = fillColor;
        ringFillImg.fillAmount = fill;
    }

    // Issue 3: says out loud why a check did not result in a capture.
    // Logs immediately when the reason changes, then at most every 2s while it stays the same.
    void CaptureDiag(string msg)
    {
        if (msg != captureHint)
        {
            captureHint = msg;
            if (state == State.Capturing && infoText != null) infoText.text = BuildCaptureText();
        }
        if (!logCaptureDiagnostics) return;
        if (msg == lastCaptureDiag && Time.time < nextDiagTime) return;
        lastCaptureDiag = msg;
        nextDiagTime = Time.time + 2f;
        Debug.Log($"[AppFlow][cap] {msg}  ({capturedCount}/{cells.Count} captured)");
    }

    string BuildCaptureText()
    {
        return $"<b>Capturing room</b>\n{ProgressBar(capturedCount, cells.Count)}  {capturedCount} / {cells.Count}\n\n{captureHint}";
    }

    // ASCII only, so it renders with any font asset.
    static string ProgressBar(int done, int total, int width = 14)
    {
        if (total <= 0) return "";
        int filled = Mathf.Clamp(Mathf.RoundToInt((float)done / total * width), 0, width);
        return "<mspace=0.6em>[" + new string('#', filled) + new string('-', width - filled) + "]</mspace>";
    }

    // Points the user at the closest cell that still needs a capture.
    string NearestCellHint(Vector3 from)
    {
        CaptureCell best = null;
        float bestSqr = float.MaxValue;
        foreach (var c in cells)
        {
            if (c.captured) continue;
            // standPoint, not worldCenter: the centre of a cell can be inside a table.
            float d = (c.standPoint - from).sqrMagnitude;
            if (d < bestSqr) { bestSqr = d; best = c; }
        }
        if (best == null) return "";

        Vector3 delta = best.standPoint - from;
        delta.y = 0f;
        float dist = delta.magnitude;
        if (headCam == null) return $"Nearest spot is {dist:F1} m away.";

        Vector3 fwd = headCam.transform.forward; fwd.y = 0f;
        if (fwd.sqrMagnitude < 1e-4f) return $"Nearest spot is {dist:F1} m away.";

        float signed = Vector3.SignedAngle(fwd.normalized, delta.normalized, Vector3.up);
        string dir = Mathf.Abs(signed) < 30f ? "ahead"
                   : Mathf.Abs(signed) > 150f ? "behind you"
                   : signed > 0f ? "to your right" : "to your left";
        return $"Nearest spot: {dist:F1} m {dir}.";
    }

    // Keeps the panel in front of the user without jittering while they aim at it.
    void UpdatePanelPlacement()
    {
        if (panelRoot == null || headCam == null) return;

        Transform head = headCam.transform;
        Vector3 fwd = head.forward; fwd.y = 0f;
        if (fwd.sqrMagnitude < 1e-4f) return;
        fwd.Normalize();

        Vector3 toPanel = panelRoot.position - head.position; toPanel.y = 0f;
        float angle = toPanel.sqrMagnitude < 1e-4f ? 180f : Vector3.Angle(fwd, toPanel.normalized);

        if (!panelFollowing && angle > panelFollowAngle) panelFollowing = true;
        else if (panelFollowing && angle < 4f) panelFollowing = false;
        if (!panelFollowing) return;

        Vector3 target = head.position + fwd * panelDistance;
        // Drop the panel clear of the aim ring, which owns the centre of view while capturing.
        target.y = head.position.y + panelHeightOffset - (ringVisible ? 0.45f : 0f);

        float k = 1f - Mathf.Exp(-panelFollowSpeed * Time.deltaTime);
        panelRoot.position = Vector3.Lerp(panelRoot.position, target, k);

        Vector3 look = panelRoot.position - head.position; look.y = 0f;
        if (look.sqrMagnitude > 1e-4f)
            panelRoot.rotation = Quaternion.Slerp(panelRoot.rotation, Quaternion.LookRotation(look), k);
    }

    CaptureCell FindCellForPosition(Vector3 worldPos)
    {
        float half = segmentSize * 0.5f;
        foreach (var c in cells)
        {
            if (Mathf.Abs(worldPos.x - c.worldCenter.x) <= half &&
                Mathf.Abs(worldPos.z - c.worldCenter.z) <= half)
                return c;
        }
        return null;
    }

    float MeasureDepthAhead(Vector3 origin, Vector3 direction)
    {
        MRUKRoom room = MRUK.Instance.GetCurrentRoom();
        if (room == null) return 0f;   // no room -> no measurable depth, never capture (was an NRE)

        Ray ray = new Ray(origin, direction);
        const float maxDist = 20f;

        if (room.Raycast(ray, maxDist, out RaycastHit hit))
            return hit.distance;
        return maxDist;
    }

    bool CaptureFrame()
    {
        if (cameraAccess == null || !cameraAccess.IsPlaying)
        {
            CaptureDiag("Waiting for the passthrough camera to start...");
            return false;
        }

        Texture src = cameraAccess.GetTexture();
        if (src == null)
        {
            CaptureDiag("Passthrough camera returned no frame yet...");
            return false;
        }

        RenderTexture rt = RenderTexture.GetTemporary(src.width, src.height, 0);
        Graphics.Blit(src, rt);
        RenderTexture prev = RenderTexture.active;
        RenderTexture.active = rt;
        Texture2D tex = new Texture2D(src.width, src.height, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, src.width, src.height), 0, 0);
        tex.Apply();
        RenderTexture.active = prev;
        RenderTexture.ReleaseTemporary(rt);

        byte[] jpg = tex.EncodeToJPG(85);
        capturedFrames.Add(jpg);          // ← new: keep in memory for later POST

        string path = Path.Combine(Application.persistentDataPath,
            $"capture_{System.DateTime.Now:HHmmss_fff}.jpg");
        File.WriteAllBytes(path, jpg);
        Destroy(tex);

        Debug.Log($"[AppFlow] Saved {jpg.Length} bytes to {path}");
        return true;
    }

    void SetState(State newState, string message, bool showButton = true)
    {
        state = newState;
        infoText.text = message;
        okButton.gameObject.SetActive(showButton);
        Debug.Log($"[AppFlow] → {newState}");
        if (logUiDiagnostics) LogInfoTextDiagnostics(newState);
    }

    // Issue 2: dump everything that can make a TMP label invisible in a World Space canvas.
    void LogInfoTextDiagnostics(State forState)
    {
        if (infoText == null)
        {
            Debug.LogError("[AppFlow][ui] infoText reference is NULL - nothing can render.");
            return;
        }

        infoText.ForceMeshUpdate();   // make textInfo reflect the string we just assigned

        RectTransform rt = infoText.rectTransform;
        Rect r = rt.rect;
        Vector3[] corners = new Vector3[4];
        rt.GetWorldCorners(corners);
        float worldW = Vector3.Distance(corners[0], corners[3]);
        float worldH = Vector3.Distance(corners[0], corners[1]);

        TMP_FontAsset font = infoText.font;
        string fontInfo = font == null
            ? "NULL  <-- no font asset assigned (import TMP Essential Resources)"
            : $"'{font.name}' atlas={(font.atlasTexture == null ? "NULL" : $"{font.atlasTexture.width}x{font.atlasTexture.height}")} glyphs={(font.glyphTable == null ? -1 : font.glyphTable.Count)}";

        int verts = (infoText.textInfo != null && infoText.textInfo.meshInfo != null && infoText.textInfo.meshInfo.Length > 0)
            ? infoText.textInfo.meshInfo[0].vertexCount : -1;

        // parent chain: per-level active flag and any CanvasGroup alpha that could hide us
        StringBuilder chain = new StringBuilder();
        float groupAlpha = 1f;
        for (Transform t = infoText.transform; t != null; t = t.parent)
        {
            CanvasGroup cg = t.GetComponent<CanvasGroup>();
            if (cg != null) groupAlpha *= cg.alpha;
            chain.Insert(0, $"/{t.name}[{(t.gameObject.activeSelf ? "on" : "OFF")}{(cg != null ? $",cg={cg.alpha:F2}" : "")}]");
        }

        // sibling order: inside a Canvas, LATER siblings draw ON TOP of earlier ones
        StringBuilder sibs = new StringBuilder();
        Transform parent = infoText.transform.parent;
        if (parent != null)
            for (int i = 0; i < parent.childCount; i++)
                sibs.Append($"{i}:{parent.GetChild(i).name} ");

        Debug.Log(
            $"[AppFlow][ui] state={forState} textLen={infoText.text.Length} renderedChars={infoText.textInfo?.characterCount ?? -1} meshVerts={verts}\n" +
            $"[AppFlow][ui]   rect={r.width:F1}x{r.height:F1}px worldSize={worldW:F3}x{worldH:F3}m lossyScale={rt.lossyScale}\n" +
            $"[AppFlow][ui]   activeInHierarchy={infoText.gameObject.activeInHierarchy} enabled={infoText.enabled} crAlpha={infoText.canvasRenderer.GetAlpha():F2} canvasGroupAlpha={groupAlpha:F2}\n" +
            $"[AppFlow][ui]   color={infoText.color} fontSize={infoText.fontSize:F1} autoSize={infoText.enableAutoSizing} overflow={infoText.overflowMode} overflowing={infoText.isTextOverflowing}\n" +
            $"[AppFlow][ui]   font={fontInfo}\n" +
            $"[AppFlow][ui]   siblingIndex={infoText.transform.GetSiblingIndex()} siblings=[{sibs}]\n" +
            $"[AppFlow][ui]   chain={chain}");
    }

    // Volumes a person has to walk around. Rebuilt on every segmentation so a re-scan
    // picks up moved furniture.
    private readonly List<MRUKAnchor> floorObstacles = new List<MRUKAnchor>();
    private readonly List<Vector3> freeSamples = new List<Vector3>();

    // These bound the room rather than stand on its floor, so they never block a cell.
    private const MRUKAnchor.SceneLabels StructureLabels =
        MRUKAnchor.SceneLabels.FLOOR | MRUKAnchor.SceneLabels.CEILING |
        MRUKAnchor.SceneLabels.WALL_FACE | MRUKAnchor.SceneLabels.INVISIBLE_WALL_FACE |
        MRUKAnchor.SceneLabels.INNER_WALL_FACE | MRUKAnchor.SceneLabels.GLOBAL_MESH |
        MRUKAnchor.SceneLabels.DOOR_FRAME | MRUKAnchor.SceneLabels.WINDOW_FRAME |
        MRUKAnchor.SceneLabels.WALL_ART;

    void CollectFloorObstacles(MRUKRoom room, float floorY)
    {
        floorObstacles.Clear();
        if (room.Anchors == null) return;

        foreach (MRUKAnchor a in room.Anchors)
        {
            if (a == null || !a.VolumeBounds.HasValue) continue;   // planes have no footprint to block
            if ((a.Label & StructureLabels) != 0) continue;

            // A volume only takes floor away if it reaches down to it. A wall-mounted screen
            // or a high shelf has a volume but leaves the floor underneath walkable.
            if (VolumeWorldMinY(a) > floorY + floorObstacleMaxHeight) continue;

            floorObstacles.Add(a);
        }
    }

    // A volume's vertical axis is the anchor's local Z and anchors carry an arbitrary yaw,
    // so read the height off the transformed corners rather than assuming an axis.
    static float VolumeWorldMinY(MRUKAnchor a)
    {
        Bounds b = a.VolumeBounds.Value;
        Vector3 lo = b.min, hi = b.max;
        float minY = float.MaxValue;
        for (int i = 0; i < 8; i++)
        {
            Vector3 corner = new Vector3(
                (i & 1) == 0 ? lo.x : hi.x,
                (i & 2) == 0 ? lo.y : hi.y,
                (i & 4) == 0 ? lo.z : hi.z);
            minY = Mathf.Min(minY, a.transform.TransformPoint(corner).y);
        }
        return minY;
    }

    // testVerticalBounds:false tests the volume's local X/Y, which is its horizontal
    // footprint (local Z is the vertical axis). Bounds.Expand grows the total size, so the
    // per-side clearance is half of what we pass in.
    bool IsBlockedByFurniture(Vector3 p)
    {
        foreach (MRUKAnchor a in floorObstacles)
            if (a.IsPositionInVolume(p, testVerticalBounds: false, personRadius * 2f))
                return true;
        return false;
    }

    bool IsStandableFloor(MRUKRoom room, Vector3 p)
    {
        return room.IsPositionInRoom(p, testVerticalBounds: false) && !IsBlockedByFurniture(p);
    }

    // Fraction of the cell that is standable floor, plus a point inside that free area.
    float MeasureCellFloor(MRUKRoom room, Vector3 center, out Vector3 standPoint, out float inRoomRatio)
    {
        int n = Mathf.Max(3, floorSamplesPerAxis);
        float step = segmentSize / n;
        float first = -segmentSize * 0.5f + step * 0.5f;
        int inRoom = 0;

        freeSamples.Clear();
        for (int ix = 0; ix < n; ix++)
        {
            for (int iz = 0; iz < n; iz++)
            {
                Vector3 p = new Vector3(center.x + first + ix * step, center.y, center.z + first + iz * step);
                if (!room.IsPositionInRoom(p, testVerticalBounds: false)) continue;
                inRoom++;
                if (!IsBlockedByFurniture(p)) freeSamples.Add(p);
            }
        }

        inRoomRatio = (float)inRoom / (n * n);
        if (freeSamples.Count == 0) { standPoint = center; return 0f; }

        Vector3 centroid = Vector3.zero;
        foreach (Vector3 p in freeSamples) centroid += p;
        centroid /= freeSamples.Count;

        if (IsStandableFloor(room, centroid))
        {
            standPoint = centroid;
        }
        else
        {
            // The free area can be C-shaped, in which case its centroid lands on the very
            // furniture it wraps around. Fall back to the free sample closest to it.
            standPoint = freeSamples[0];
            float best = float.MaxValue;
            foreach (Vector3 p in freeSamples)
            {
                float d = (p - centroid).sqrMagnitude;
                if (d < best) { best = d; standPoint = p; }
            }
        }
        return (float)freeSamples.Count / (n * n);
    }

    void SegmentRoom()
    {
        cells.Clear();
        MRUKRoom room = MRUK.Instance.GetCurrentRoom();
        if (room == null) { Debug.LogError("[AppFlow] No room!"); return; }

        Bounds bounds = room.GetRoomBounds();
        Vector3 min = bounds.min;
        Vector3 max = bounds.max;

        int gridCountX = Mathf.CeilToInt((max.x - min.x) / segmentSize);
        int gridCountZ = Mathf.CeilToInt((max.z - min.z) / segmentSize);

        float floorY = (room.FloorAnchors != null && room.FloorAnchors.Count > 0)
            ? room.FloorAnchors[0].transform.position.y
            : min.y;

        CollectFloorObstacles(room, floorY);

        int rejectedOutside = 0, rejectedFurniture = 0, rejectedTooTight = 0;

        for (int gx = 0; gx < gridCountX; gx++)
        {
            for (int gz = 0; gz < gridCountZ; gz++)
            {
                Vector3 center = new Vector3(
                    min.x + (gx + 0.5f) * segmentSize,
                    floorY + 0.05f,
                    min.z + (gz + 0.5f) * segmentSize
                );

                // The centre alone says nothing useful: it can sit inside a table while most
                // of the cell is walkable, or on clear floor in a cell that is 90% wall.
                // Sample the whole cell and keep only what a person can actually stand on.
                float freeRatio = MeasureCellFloor(room, center, out Vector3 standPoint, out float inRoomRatio);

                if (inRoomRatio <= 0f) { rejectedOutside++; continue; }
                if (freeRatio <= 0f) { rejectedFurniture++; continue; }
                if (freeRatio < minFreeFloorRatio) { rejectedTooTight++; continue; }

                cells.Add(new CaptureCell
                {
                    gridX = gx,
                    gridZ = gz,
                    worldCenter = center,
                    standPoint = standPoint,
                    freeRatio = freeRatio,
                    captured = false
                });
            }
        }

        Debug.Log($"[AppFlow] Segmented floor: grid {gridCountX}x{gridCountZ} -> {cells.Count} standable cells " +
                  $"(room bounds {bounds.size.x:F2}x{bounds.size.z:F2}m, cell {segmentSize:F2}m, floorY {floorY:F2}, " +
                  $"{floorObstacles.Count} floor obstacle(s)). Rejected: {rejectedOutside} outside the room, " +
                  $"{rejectedFurniture} fully covered by furniture, {rejectedTooTight} under {minFreeFloorRatio:P0} free floor.");
        foreach (MRUKAnchor a in floorObstacles)
            Debug.Log($"[AppFlow]   obstacle {a.Label} at {a.transform.position} size {a.VolumeBounds.Value.size}");
        foreach (var c in cells)
            Debug.Log($"[AppFlow]   cell ({c.gridX},{c.gridZ}) centre {c.worldCenter} stand {c.standPoint} free {c.freeRatio:P0}");
    }

    // FastAPI

    // SendData was fire-and-forget, so anything it threw vanished and the panel sat on
    // "uploading..." forever with nothing in the log. Surface failures instead.
    async Task SendDataSafe()
    {
        try
        {
            await SendData();
        }
        catch (System.Exception e)
        {
            Debug.LogError($"[AppFlow] SendData threw: {e}");
            SetState(State.Complete, $"⚠ Upload failed\n{e.Message}", showButton: false);
        }
    }

    async Task SendData()
    {
        // Build the payload
        MRUKRoom room = MRUK.Instance.GetCurrentRoom();
        if (room == null) throw new System.InvalidOperationException("No current MRUK room to describe.");

        var anchorList = new List<AnchorData>();

        foreach (var a in room.Anchors)
        {
            var ad = new AnchorData
            {
                label = a.Label.ToString(),
                position = ToArray(a.transform.position),
                rotation = ToArray(a.transform.rotation),
                size = null
            };
            if (a.VolumeBounds.HasValue)
                ad.size = ToArray(a.VolumeBounds.Value.size);
            else if (a.PlaneRect.HasValue)
                ad.size = new float[] { a.PlaneRect.Value.size.x, a.PlaneRect.Value.size.y, 0f };
            anchorList.Add(ad);
        }

        var captures = new string[capturedFrames.Count];
        for (int i = 0; i < capturedFrames.Count; i++)
            captures[i] = System.Convert.ToBase64String(capturedFrames[i]);

        var payload = new Payload
        {
            room = new RoomData { anchors = anchorList.ToArray() },
            captures = captures
        };

        string json = JsonUtility.ToJson(payload);
        Debug.Log($"[AppFlow] Posting payload: {json.Length} chars, {captures.Length} images");

        // POST it
        string endpoint = $"{apiUrl.TrimEnd('/')}/receive-data";
        using (var req = new UnityWebRequest(endpoint, "POST"))
        {
            byte[] body = Encoding.UTF8.GetBytes(json);
            req.uploadHandler = new UploadHandlerRaw(body);
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            req.timeout = 60;

            var op = req.SendWebRequest();
            while (!op.isDone) await Task.Yield();

            if (req.result == UnityWebRequest.Result.Success)
            {
                Debug.Log($"[AppFlow] Server response: {req.downloadHandler.text}");
                SetState(State.Complete,
                    $"<b>✓ Done</b>\n{captures.Length} images uploaded.\n{anchorList.Count} anchors sent.",
                    showButton: false);
            }
            else
            {
                Debug.LogError($"[AppFlow] POST failed: {req.error} — {req.downloadHandler.text}");
                SetState(State.Complete,
                    $"<b>⚠ Upload failed</b>\n{req.error}\n{endpoint}",
                    showButton: false);
            }
        }
    }

    static float[] ToArray(Vector3 v) => new float[] { v.x, v.y, v.z };
    static float[] ToArray(Quaternion q) => new float[] { q.x, q.y, q.z, q.w };
}