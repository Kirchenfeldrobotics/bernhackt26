using UnityEngine;
using TMPro;

/// <summary>
/// Main controller — orchestrates the entire app flow.
/// 
/// Attach to a single GameObject and drag all references in the Inspector.
/// This script talks to ScreenManager, PermissionHandler, RoomScanner,
/// CaptureGuide, ApiClient, and ResultsDisplay.
/// </summary>
public class AppController : MonoBehaviour
{
    [Header("Script references (drag GameObjects)")]
    [SerializeField] private ScreenManager screenManager;
    [SerializeField] private PermissionHandler permissionHandler;
    [SerializeField] private RoomScanner roomScanner;
    [SerializeField] private CaptureGuide captureGuide;
    [SerializeField] private ApiClient apiClient;
    [SerializeField] private ResultsDisplay resultsDisplay;

    [Header("Capture status UI")]
    [SerializeField] private TMP_Text captureStatusText;

    [Header("Camera")]
    [SerializeField] private Transform centerEyeAnchor;

    [Header("Fallback")]
    [SerializeField] private string fallbackBusinessName = "Demo Firma";

    private Camera headCam;

    private string ResolvedBusinessName
    {
        get
        {
            string bn = screenManager != null ? screenManager.BusinessName : "";
            return string.IsNullOrWhiteSpace(bn) ? fallbackBusinessName : bn;
        }
    }

    async void Start()
    {
        headCam = ResolveHeadCamera();
        resultsDisplay.Initialize(screenManager);

        // Wire up events
        captureGuide.OnStatusChanged += OnCaptureStatusChanged;
        captureGuide.OnCaptureProgress += OnCaptureProgress;
        captureGuide.OnAllCaptured += OnAllCapturesDone;

        // Start at screen 1
        screenManager.Show(ScreenManager.Screen.Start);

        // Request permissions in background
        bool permsOk = await permissionHandler.RequestAllPermissions();
        if (!permsOk)
        {
            screenManager.SetWaitingText("Permissions denied.\nGrant them in Settings and restart.");
            screenManager.Show(ScreenManager.Screen.Waiting);
            return;
        }

        // Check for existing room scan
        bool hasRoom = await roomScanner.TryLoadExistingRoom();
        Debug.Log($"[AppController] Existing room scan: {hasRoom}");
    }

    // --- Notfall-Navigation per Controller-Taste (unabhaengig vom UI) ---
    // A / X  = weiter    |    B / Y = zurueck zu Screen 1

    void Update()
    {
        if (screenManager == null) return;

        if (OVRInput.GetDown(OVRInput.Button.One))
        {
            Debug.Log($"[AppController] A-Taste, Screen={screenManager.CurrentScreen}");
            AdvanceCurrentScreen();
        }
        else if (OVRInput.GetDown(OVRInput.Button.Two))
        {
            Debug.Log("[AppController] B-Taste -> Start");
            screenManager.Show(ScreenManager.Screen.Start);
        }
    }

    private void AdvanceCurrentScreen()
    {
        switch (screenManager.CurrentScreen)
        {
            case ScreenManager.Screen.Start:
                OnNewScanClicked();
                break;
            case ScreenManager.Screen.InfoAndScanStart:
                OnStartScanClicked();
                break;
            case ScreenManager.Screen.InformationWindow:
                OnCloseInfoWindow();
                break;
            default:
                Debug.Log("[AppController] Kein Weiter fuer diesen Screen.");
                break;
        }
    }

    // --- Button callbacks (assign in Inspector via OnClick) ---

    /// <summary>
    /// Called by "New Scan" button on Screen 1.
    /// </summary>
    public void OnNewScanClicked()
    {
        Debug.Log($"[AppController] New scan for: {ResolvedBusinessName}");
        screenManager.Show(ScreenManager.Screen.InfoAndScanStart);
    }

    /// <summary>
    /// Called by "Choose from existing" button on Screen 1.
    /// TODO: implement scan selection UI.
    /// </summary>
    public void OnChooseExistingClicked()
    {
        Debug.Log("[AppController] Choose existing — not yet implemented.");
    }

    /// <summary>
    /// Called by "Start Scan" button on Screen 2.
    /// </summary>
    public async void OnStartScanClicked()
    {
        screenManager.Show(ScreenManager.Screen.Waiting);
        screenManager.SetWaitingText("Launching Space Setup...\nFollow the on-screen instructions.");

        bool success;
        if (roomScanner.HasRoom)
        {
            success = true; // Already have a room scan
        }
        else
        {
            success = await roomScanner.StartRoomScan();
        }

        if (success)
        {
            StartCapturePhase();
        }
        else
        {
            screenManager.SetWaitingText("Scan failed. Please try again.");
            screenManager.Show(ScreenManager.Screen.InfoAndScanStart);
        }
    }

    /// <summary>
    /// Called by "Cancel" button on Screen 2.
    /// </summary>
    public void OnBackToStartClicked()
    {
        screenManager.Show(ScreenManager.Screen.Start);
    }

    /// <summary>
    /// Called by close/back button on Screen 5 (Information Window).
    /// Goes back to the AR view with dots visible.
    /// </summary>
    public void OnCloseInfoWindow()
    {
        screenManager.HideAll();
        // Dots remain visible in the room
    }

    // --- Capture phase ---

    private void StartCapturePhase()
    {
        roomScanner.SegmentRoom();

        if (roomScanner.Cells.Count == 0)
        {
            screenManager.SetWaitingText("No walkable floor found.\nTry rescanning the room.");
            screenManager.Show(ScreenManager.Screen.Waiting);
            return;
        }

        // Hide all screens — the user sees passthrough + floor markers + ring
        screenManager.HideAll();

        if (headCam == null) headCam = ResolveHeadCamera();
        captureGuide.StartCapture(roomScanner, headCam);
    }

    private void OnCaptureStatusChanged(string status)
    {
        if (captureStatusText != null)
            captureStatusText.text = status;
    }

    private void OnCaptureProgress(int done, int total)
    {
        Debug.Log($"[AppController] Capture progress: {done}/{total}");
    }

    private async void OnAllCapturesDone()
    {
        Debug.Log("[AppController] All captures done. Uploading...");
        screenManager.Show(ScreenManager.Screen.Waiting);
        screenManager.SetWaitingText("Processing...\nYour scan is being analyzed.\nThis may take a few minutes.");

        var room = roomScanner.GetCurrentRoom();
        var response = await apiClient.SendData(
            ResolvedBusinessName,
            room,
            captureGuide.CapturedFrames
        );

        if (response != null)
        {
            screenManager.HideAll();
            resultsDisplay.ShowResults(response);
            Debug.Log("[AppController] Results displayed in room.");
        }
        else
        {
            screenManager.SetWaitingText("Upload failed.\nCheck your connection and try again.");
        }
    }

    // --- Helpers ---

    private Camera ResolveHeadCamera()
    {
        if (centerEyeAnchor != null)
        {
            Camera c = centerEyeAnchor.GetComponent<Camera>();
            if (c != null) return c;
        }

        OVRCameraRig rig = FindAnyObjectByType<OVRCameraRig>();
        if (rig != null && rig.centerEyeAnchor != null)
        {
            Camera c = rig.centerEyeAnchor.GetComponent<Camera>();
            if (c != null) return c;
        }

        foreach (Camera c in Camera.allCameras)
            if (c.name == "CenterEyeAnchor") return c;

        Debug.LogWarning("[AppController] Falling back to Camera.main");
        return Camera.main;
    }
}
