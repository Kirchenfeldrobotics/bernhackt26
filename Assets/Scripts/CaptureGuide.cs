using System.Collections.Generic;
using System.IO;
using Meta.XR;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Guides the user through the room capture process.
/// Spawns floor markers and an aim ring (all as prefabs from the Inspector).
/// Takes photos when the user is aligned correctly.
/// </summary>
public class CaptureGuide : MonoBehaviour
{
    [Header("Prefabs (drag from Project)")]
    [SerializeField] private GameObject floorMarkerPrefab;
    [SerializeField] private GameObject arrowPrefab;
    [SerializeField] private GameObject aimRingPrefab;

    [Header("References")]
    [SerializeField] private PassthroughCameraAccess cameraAccess;

    [Header("Aim settings")]
    [SerializeField] private float aimTolerance = 20f;
    [SerializeField] private float aimHoldTime = 1.4f;
    [SerializeField] private float maxAimTurnRate = 45f;
    [SerializeField] private float ringDistance = 2f;

    [Header("Capture")]
    [SerializeField] private float checkInterval = 0.25f;

    [Header("Colors")]
    [SerializeField] private Color colorIdle = new Color(1f, 1f, 1f, 0.30f);
    [SerializeField] private Color colorArmed = new Color(0.35f, 1f, 0.55f, 0.55f);
    [SerializeField] private Color colorBlocked = new Color(1f, 0.72f, 0.20f, 0.60f);
    [SerializeField] private Color colorConfirm = new Color(0.35f, 1f, 0.55f, 0.90f);
    [SerializeField] private Color colorFill = new Color(0.35f, 1f, 0.55f, 0.95f);

    // Events
    public System.Action<int, int> OnCaptureProgress;   // (capturedCount, totalCount)
    public System.Action OnAllCaptured;                  // all cells done
    public System.Action<string> OnStatusChanged;        // status text for UI

    // State
    public bool IsCapturing { get; private set; }
    public int CapturedCount { get; private set; }
    public int TotalCells => cells != null ? cells.Count : 0;
    public List<byte[]> CapturedFrames { get; private set; } = new List<byte[]>();

    private RoomScanner roomScanner;
    private Camera headCam;
    private List<RoomScanner.CaptureCell> cells;

    private float aimProgress;
    private float confirmTimer;
    private Vector3 confirmAimDir;
    private Vector3 lastHeadForward;
    private float headTurnRate;
    private float cachedDepth;
    private float nextDepthTime;
    private float captureGraceUntil;

    // Spawned objects
    private List<GameObject> spawnedMarkers = new List<GameObject>();
    private GameObject activeArrow;
    private GameObject aimRingInstance;
    private Image ringBaseImg;
    private Image ringFillImg;

    /// <summary>
    /// Call this to start the capture process after room segmentation.
    /// </summary>
    public void StartCapture(RoomScanner scanner, Camera headCamera)
    {
        roomScanner = scanner;
        headCam = headCamera;
        cells = scanner.Cells;
        CapturedCount = 0;
        CapturedFrames.Clear();

        aimProgress = 0f;
        confirmTimer = 0f;
        headTurnRate = 0f;
        lastHeadForward = Vector3.zero;
        foreach (var c in cells) c.aimSolved = false;

        captureGraceUntil = Time.time + 1.0f;
        IsCapturing = true;

        SpawnAllFloorMarkers();
        SetStatus("Walk to a glowing marker, then face the ring.");

        Debug.Log($"[CaptureGuide] Started. {cells.Count} cells to capture.");
    }

    /// <summary>
    /// Stops the capture process and cleans up spawned objects.
    /// </summary>
    public void StopCapture()
    {
        IsCapturing = false;
        CleanupAll();
    }

    void Update()
    {
        if (!IsCapturing) return;
        if (headCam == null) return;

        Transform head = headCam.transform;
        TrackHeadTurn(head);

        // Play out confirmation animation after a shot
        if (confirmTimer > 0f)
        {
            confirmTimer -= Time.deltaTime;
            float t = 1f - Mathf.Clamp01(confirmTimer / Mathf.Max(0.05f, aimHoldTime * 0.5f));
            UpdateRing(head, confirmAimDir, 0.5f + 0.5f * t, colorConfirm, colorFill);
            if (confirmTimer <= 0f) { aimProgress = 0f; ShowRing(false); }
            return;
        }

        if (Time.time < captureGraceUntil) { ShowRing(false); return; }

        if (cameraAccess == null || !cameraAccess.IsPlaying)
        {
            ShowRing(false);
            SetStatus("Waiting for the passthrough camera...");
            return;
        }

        var cell = roomScanner.FindCellAtPosition(head.position);
        if (cell == null || cell.captured)
        {
            ShowRing(false);
            aimProgress = 0f;
            SetStatus(cell == null
                ? $"Move to a glowing marker. {NearestCellHint(head)}"
                : $"This spot is done. {NearestCellHint(head)}");
            return;
        }

        UpdateAiming(head, cell);
    }

    private void UpdateAiming(Transform head, RoomScanner.CaptureCell cell)
    {
        Vector3 gaze = Flat(head.forward);
        if (gaze == Vector3.zero) return;

        if (!cell.aimSolved ||
            (aimProgress <= 0f && (head.position - cell.aimAnchor).sqrMagnitude > 0.25f))
            SolveAim(cell, head.position);

        if (Time.time >= nextDepthTime)
        {
            nextDepthTime = Time.time + Mathf.Max(0.02f, checkInterval);
            cachedDepth = roomScanner.MeasureDepthAhead(head.position, head.forward);
        }

        float off = Vector3.Angle(gaze, cell.aimDirection);
        bool onTarget = off <= aimTolerance;
        bool steady = headTurnRate <= maxAimTurnRate;
        bool deep = cachedDepth >= cell.requiredDepth;

        if (onTarget && steady && deep)
        {
            float before = aimProgress;
            aimProgress = Mathf.Min(1f, aimProgress + Time.deltaTime / Mathf.Max(0.2f, aimHoldTime));
            SetStatus("Hold still...");
            if (before < 0.5f && aimProgress >= 0.5f) TryCapture(cell, head);
        }
        else
        {
            aimProgress = 0f;
            if (!onTarget) SetStatus($"Turn to face the ring ({off:F0}° off).");
            else if (!steady) SetStatus("Slow down — hold still inside the ring.");
            else SetStatus($"No open view — need {cell.requiredDepth:F1}m, got {cachedDepth:F1}m.");
        }

        Color baseCol = !onTarget ? colorIdle : (deep && steady ? colorArmed : colorBlocked);
        UpdateRing(head, cell.aimDirection, aimProgress, baseCol, colorFill);
    }

    private void TryCapture(RoomScanner.CaptureCell cell, Transform head)
    {
        float depth = roomScanner.MeasureDepthAhead(head.position, head.forward);
        if (depth < cell.requiredDepth)
        {
            aimProgress = 0f;
            SetStatus("Lost the view — line up again.");
            return;
        }

        if (!CaptureFrame()) { aimProgress = 0f; return; }

        cell.captured = true;
        CapturedCount++;
        confirmAimDir = cell.aimDirection;
        confirmTimer = Mathf.Max(0.15f, aimHoldTime * 0.5f);

        // Remove the floor marker for this cell
        RemoveMarkerForCell(cell);

        Debug.Log($"[CaptureGuide] Captured ({cell.gridX},{cell.gridZ}) -> {CapturedCount}/{cells.Count}");
        OnCaptureProgress?.Invoke(CapturedCount, cells.Count);

        if (CapturedCount >= cells.Count)
        {
            IsCapturing = false;
            SetStatus("All captures complete!");
            OnAllCaptured?.Invoke();
        }
        else
        {
            SetStatus("Got it! Move to the next marker.");
        }
    }

    // --- Floor markers ---

    private void SpawnAllFloorMarkers()
    {
        if (floorMarkerPrefab == null)
        {
            Debug.LogWarning("[CaptureGuide] No floorMarkerPrefab assigned!");
            return;
        }

        foreach (var cell in cells)
        {
            if (cell.captured) continue;
            GameObject marker = Instantiate(floorMarkerPrefab, cell.standPoint, Quaternion.identity);
            marker.name = $"FloorMarker_{cell.gridX}_{cell.gridZ}";
            spawnedMarkers.Add(marker);
        }
    }

    private void RemoveMarkerForCell(RoomScanner.CaptureCell cell)
    {
        string name = $"FloorMarker_{cell.gridX}_{cell.gridZ}";
        for (int i = spawnedMarkers.Count - 1; i >= 0; i--)
        {
            if (spawnedMarkers[i] != null && spawnedMarkers[i].name == name)
            {
                Destroy(spawnedMarkers[i]);
                spawnedMarkers.RemoveAt(i);
            }
        }
    }

    // --- Aim ring (prefab-based) ---

    private void ShowRing(bool show)
    {
        if (aimRingInstance == null && show) SpawnRing();
        if (aimRingInstance != null) aimRingInstance.SetActive(show);
    }

    private void SpawnRing()
    {
        if (aimRingPrefab == null)
        {
            Debug.LogWarning("[CaptureGuide] No aimRingPrefab assigned!");
            return;
        }

        aimRingInstance = Instantiate(aimRingPrefab);
        aimRingInstance.name = "AimRing";

        // Expect the prefab to have two Image children: "Base" and "Fill"
        var images = aimRingInstance.GetComponentsInChildren<Image>(true);
        foreach (var img in images)
        {
            if (img.gameObject.name == "Base") ringBaseImg = img;
            else if (img.gameObject.name == "Fill")
            {
                ringFillImg = img;
                ringFillImg.type = Image.Type.Filled;
                ringFillImg.fillMethod = Image.FillMethod.Radial360;
                ringFillImg.fillOrigin = (int)Image.Origin360.Top;
                ringFillImg.fillClockwise = true;
            }
        }

        aimRingInstance.SetActive(false);
    }

    private void UpdateRing(Transform head, Vector3 aimDir, float fill, Color baseColor, Color fillColor)
    {
        if (aimDir == Vector3.zero) { ShowRing(false); return; }
        ShowRing(true);

        if (aimRingInstance == null) return;

        Vector3 centre = head.position + aimDir * ringDistance;
        aimRingInstance.transform.SetPositionAndRotation(centre, Quaternion.LookRotation(aimDir, Vector3.up));

        float d = 2f * ringDistance * Mathf.Tan(aimTolerance * Mathf.Deg2Rad);
        aimRingInstance.transform.localScale = Vector3.one * d;

        if (ringBaseImg != null) ringBaseImg.color = baseColor;
        if (ringFillImg != null)
        {
            ringFillImg.color = fillColor;
            ringFillImg.fillAmount = fill;
        }
    }

    // --- Photo capture ---

    private bool CaptureFrame()
    {
        if (cameraAccess == null || !cameraAccess.IsPlaying) return false;

        Texture src = cameraAccess.GetTexture();
        if (src == null) return false;

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
        CapturedFrames.Add(jpg);

        string path = Path.Combine(Application.persistentDataPath,
            $"capture_{System.DateTime.Now:HHmmss_fff}.jpg");
        File.WriteAllBytes(path, jpg);
        Destroy(tex);

        Debug.Log($"[CaptureGuide] Saved {jpg.Length} bytes -> {path}");
        return true;
    }

    // --- Aim solving (from Nils' logic) ---

    private void SolveAim(RoomScanner.CaptureCell cell, Vector3 from)
    {
        cell.aimAnchor = from;
        cell.aimSolved = true;
        float minDepth = roomScanner.MinCaptureDepth;
        Vector3 centroid = roomScanner.RoomCentroid;

        if ((centroid - from).sqrMagnitude <= 1f)
        {
            cell.aimDirection = MostNovelDirection(cell, from, out float dm, minDepth);
            cell.aimRelaxed = dm < minDepth;
            cell.requiredDepth = cell.aimRelaxed ? Mathf.Max(0.5f, dm * 0.9f) : minDepth;
            return;
        }

        Vector3 preferred = Flat(centroid - from);
        float depth = roomScanner.MeasureDepthAhead(from, preferred);
        if (depth >= minDepth)
        {
            cell.aimDirection = preferred;
            cell.requiredDepth = minDepth;
            cell.aimRelaxed = false;
            return;
        }

        Vector3 best = preferred;
        float bestDepth = depth;
        for (int step = 1; step <= 12; step++)
        {
            for (int sign = -1; sign <= 1; sign += 2)
            {
                Vector3 dir = Quaternion.AngleAxis(step * 15f * sign, Vector3.up) * preferred;
                float d = roomScanner.MeasureDepthAhead(from, dir);
                if (d > bestDepth) { bestDepth = d; best = dir; }
                if (d >= minDepth)
                {
                    cell.aimDirection = dir;
                    cell.requiredDepth = minDepth;
                    cell.aimRelaxed = false;
                    return;
                }
                if (step == 12) break;
            }
        }

        cell.aimDirection = best;
        cell.requiredDepth = Mathf.Max(0.5f, bestDepth * 0.9f);
        cell.aimRelaxed = true;
    }

    private Vector3 MostNovelDirection(RoomScanner.CaptureCell forCell, Vector3 from, out float depth, float minDepth)
    {
        Vector3 best = Vector3.forward;
        float bestScore = float.MinValue;
        depth = 0f;

        for (int i = 0; i < 24; i++)
        {
            Vector3 dir = Quaternion.AngleAxis(i * 15f, Vector3.up) * Vector3.forward;
            float d = roomScanner.MeasureDepthAhead(from, dir);

            float novelty = 180f;
            foreach (var c in cells)
                if (c != null && c != forCell && c.aimSolved && c.aimDirection != Vector3.zero)
                    novelty = Mathf.Min(novelty, Vector3.Angle(dir, c.aimDirection));

            float score = d >= minDepth ? 1000f + novelty : d * 100f;
            if (score > bestScore) { bestScore = score; best = dir; depth = d; }
        }
        return best;
    }

    // --- Helpers ---

    private void TrackHeadTurn(Transform head)
    {
        Vector3 f = head.forward;
        if (lastHeadForward != Vector3.zero && Time.deltaTime > 1e-5f)
        {
            float instant = Vector3.Angle(lastHeadForward, f) / Time.deltaTime;
            headTurnRate = Mathf.Lerp(headTurnRate, instant, 0.35f);
        }
        lastHeadForward = f;
    }

    private string NearestCellHint(Transform head)
    {
        RoomScanner.CaptureCell best = null;
        float bestSqr = float.MaxValue;
        foreach (var c in cells)
        {
            if (c.captured) continue;
            float d = (c.standPoint - head.position).sqrMagnitude;
            if (d < bestSqr) { bestSqr = d; best = c; }
        }
        if (best == null) return "";

        Vector3 delta = best.standPoint - head.position;
        delta.y = 0f;
        float dist = delta.magnitude;

        Vector3 fwd = head.forward; fwd.y = 0f;
        if (fwd.sqrMagnitude < 1e-4f) return $"Nearest: {dist:F1}m away.";

        float signed = Vector3.SignedAngle(fwd.normalized, delta.normalized, Vector3.up);
        string dir = Mathf.Abs(signed) < 30f ? "ahead"
                   : Mathf.Abs(signed) > 150f ? "behind you"
                   : signed > 0f ? "to your right" : "to your left";
        return $"Nearest: {dist:F1}m {dir}.";
    }

    private void SetStatus(string msg)
    {
        OnStatusChanged?.Invoke(msg);
    }

    private void CleanupAll()
    {
        foreach (var m in spawnedMarkers) if (m != null) Destroy(m);
        spawnedMarkers.Clear();
        if (activeArrow != null) Destroy(activeArrow);
        if (aimRingInstance != null) Destroy(aimRingInstance);
    }

    private void OnDestroy()
    {
        CleanupAll();
    }

    private static Vector3 Flat(Vector3 v)
    {
        v.y = 0f;
        return v.sqrMagnitude > 1e-6f ? v.normalized : Vector3.zero;
    }
}
