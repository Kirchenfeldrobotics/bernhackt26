using UnityEngine;
using TMPro;
using System.Collections.Generic;
using System.Text;

/// <summary>
/// Displays improvement suggestions (conclusions) as interactive dots in the room.
/// Clicking a dot opens the Information Window (Screen 5) with details.
/// </summary>
public class ResultsDisplay : MonoBehaviour
{
    [Header("Prefabs")]
    [SerializeField] private GameObject infoDotPrefab;

    [Header("Info Window UI (Screen 5 elements)")]
    [SerializeField] private TMP_Text titleText;
    [SerializeField] private TMP_Text descriptionText;
    [SerializeField] private TMP_Text solutionsText;
    [SerializeField] private TMP_Text savingsText;

    private ScreenManager screenManager;
    private List<GameObject> spawnedDots = new List<GameObject>();
    private List<ApiClient.Conclusion> conclusions;

    public void Initialize(ScreenManager screens)
    {
        screenManager = screens;
    }

    /// <summary>
    /// Spawns info dots at anchor positions based on the API response.
    /// </summary>
    public void ShowResults(ApiClient.ApiResponse response)
    {
        ClearDots();

        if (response == null || response.conclusions == null || response.conclusions.Length == 0)
        {
            Debug.Log("[ResultsDisplay] No conclusions to display.");
            if (screenManager != null)
                screenManager.SetWaitingText("No improvements found for this room.");
            return;
        }

        conclusions = new List<ApiClient.Conclusion>(response.conclusions);

        foreach (var conclusion in conclusions)
        {
            if (conclusion.anchor == null || conclusion.anchor.position == null)
            {
                Debug.LogWarning($"[ResultsDisplay] Conclusion '{conclusion.title}' has no anchor position, skipping.");
                continue;
            }

            Vector3 pos = new Vector3(
                conclusion.anchor.position.x,
                conclusion.anchor.position.y,
                conclusion.anchor.position.z
            );

            SpawnDot(pos, conclusion);
        }

        Debug.Log($"[ResultsDisplay] Spawned {spawnedDots.Count} info dots.");
    }

    private void SpawnDot(Vector3 position, ApiClient.Conclusion conclusion)
    {
        if (infoDotPrefab == null)
        {
            Debug.LogWarning("[ResultsDisplay] No infoDotPrefab assigned!");
            return;
        }

        GameObject dot = Instantiate(infoDotPrefab, position, Quaternion.identity);
        dot.name = $"InfoDot_{conclusion.title}";
        spawnedDots.Add(dot);

        // Store the conclusion data on the dot so we can retrieve it on click
        var data = dot.AddComponent<InfoDotData>();
        data.Conclusion = conclusion;

        // If the dot has a button or is clickable via poke interaction,
        // the click handler needs to be set up in the prefab.
        // We add a listener if there's a Button component.
        var button = dot.GetComponentInChildren<UnityEngine.UI.Button>();
        if (button != null)
        {
            button.onClick.AddListener(() => OnDotClicked(conclusion));
        }
    }

    /// <summary>
    /// Called when a user interacts with an info dot.
    /// Opens Screen 5 with the conclusion details.
    /// </summary>
    public void OnDotClicked(ApiClient.Conclusion conclusion)
    {
        Debug.Log($"[ResultsDisplay] Dot clicked: {conclusion.title}");

        if (screenManager != null)
            screenManager.Show(ScreenManager.Screen.InformationWindow);

        if (titleText != null) titleText.text = conclusion.title ?? "";
        if (descriptionText != null) descriptionText.text = conclusion.problem ?? "";

        if (solutionsText != null)
        {
            var sb = new StringBuilder();
            if (conclusion.solutions != null)
            {
                foreach (var s in conclusion.solutions)
                {
                    sb.AppendLine(s.name ?? "");
                    if (!string.IsNullOrEmpty(s.description)) sb.AppendLine(s.description);
                    if (!string.IsNullOrEmpty(s.url)) sb.AppendLine(s.url);
                    sb.AppendLine();
                }
            }
            solutionsText.text = sb.ToString().TrimEnd();
        }

        if (savingsText != null)
        {
            savingsText.text = !string.IsNullOrEmpty(conclusion.savings_10y_chf)
                ? $"CHF {conclusion.savings_10y_chf} saved over 10 years"
                : "";
        }
    }

    public void ClearDots()
    {
        foreach (var dot in spawnedDots)
            if (dot != null) Destroy(dot);
        spawnedDots.Clear();
    }

    private void OnDestroy()
    {
        ClearDots();
    }
}

/// <summary>
/// Simple data holder attached to each info dot GameObject.
/// </summary>
public class InfoDotData : MonoBehaviour
{
    public ApiClient.Conclusion Conclusion { get; set; }
}
