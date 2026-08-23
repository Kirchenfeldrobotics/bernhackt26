using UnityEngine;
using TMPro;

/// <summary>
/// Manages the visibility of all UI screens.
/// Drag your screen GameObjects into the Inspector slots.
/// </summary>
public class ScreenManager : MonoBehaviour
{
    [Header("Screens (drag from Hierarchy)")]
    [SerializeField] private GameObject startScreen;          // 1 - Start Screen with Input Data
    [SerializeField] private GameObject infoAndScanStart;     // 2 - Information and Scan Start
    [SerializeField] private GameObject waitingScreen;        // 4 - Waiting Screen - Scan in Progress
    [SerializeField] private GameObject informationWindow;    // 5 - Information Window

    [Header("Dynamic UI elements")]
    [SerializeField] private TMP_Text waitingStatusText;      // text on the waiting screen
    [SerializeField] private TMP_InputField businessNameInput; // input field on start screen

    public string BusinessName => businessNameInput != null ? businessNameInput.text : "";

    public enum Screen
    {
        None,
        Start,
        InfoAndScanStart,
        Waiting,
        InformationWindow
    }

    private Screen currentScreen = Screen.None;

    void Awake()
    {
        HideAll();
    }

    public void Show(Screen screen)
    {
        HideAll();
        currentScreen = screen;

        GameObject target = GetScreenObject(screen);
        if (target != null)
        {
            target.SetActive(true);
            Debug.Log($"[ScreenManager] Showing: {screen}");
        }
    }

    public void HideAll()
    {
        if (startScreen != null) startScreen.SetActive(false);
        if (infoAndScanStart != null) infoAndScanStart.SetActive(false);
        if (waitingScreen != null) waitingScreen.SetActive(false);
        if (informationWindow != null) informationWindow.SetActive(false);
        currentScreen = Screen.None;
    }

    public void SetWaitingText(string text)
    {
        if (waitingStatusText != null)
            waitingStatusText.text = text;
    }

    public Screen CurrentScreen => currentScreen;

    private GameObject GetScreenObject(Screen screen)
    {
        switch (screen)
        {
            case Screen.Start: return startScreen;
            case Screen.InfoAndScanStart: return infoAndScanStart;
            case Screen.Waiting: return waitingScreen;
            case Screen.InformationWindow: return informationWindow;
            default: return null;
        }
    }
}
