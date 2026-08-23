using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using Meta.XR.MRUtilityKit;
using UnityEngine;
using UnityEngine.Networking;

/// <summary>
/// Handles communication with the FastAPI backend.
/// Sends room data + captured images, receives improvement suggestions.
/// </summary>
public class ApiClient : MonoBehaviour
{
    [Header("Backend")]
    [SerializeField] private string apiUrl = "https://bernhackt26.kirchenfeldrobotics.ch";

    // --- Data classes ---

    [System.Serializable]
    public class AnchorData
    {
        public string label;
        public float[] position;
        public float[] rotation;
        public float[] size;
    }

    [System.Serializable]
    public class RoomData
    {
        public AnchorData[] anchors;
    }

    [System.Serializable]
    public class Payload
    {
        public string businessName;
        public RoomData room;
        public string[] captures;
    }

    // Response from backend — mirrors the `Conclusion` SQLAlchemy model.
    // One entry per problem found in the room, each with its own anchor and solutions.

    [System.Serializable]
    public class SolutionData
    {
        public string id;
        public string name;
        public string url;
        public string description;
    }

    [System.Serializable]
    public class AnchorPosition
    {
        public float x;
        public float y;
        public float z;
    }

    [System.Serializable]
    public class AnchorInfo
    {
        public string label;
        public AnchorPosition position;
    }

    [System.Serializable]
    public class Conclusion
    {
        public string id;
        public string company_name;
        public string batch;
        public string title;
        public string problem;
        public SolutionData[] solutions;
        public string savings_10y_chf;
        public AnchorInfo anchor;
        public string status;
        public string created_at;
    }

    [System.Serializable]
    public class ApiResponse
    {
        public Conclusion[] conclusions;
    }

    /// <summary>
    /// Sends room data and captured images to the backend.
    /// Returns the parsed response, or null on failure.
    /// </summary>
    public async Task<ApiResponse> SendData(string businessName, MRUKRoom room, List<byte[]> capturedFrames)
    {
        if (room == null)
        {
            Debug.LogError("[ApiClient] No room to send.");
            return null;
        }

        // Build anchor list
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

        // Encode images
        var captures = new string[capturedFrames.Count];
        for (int i = 0; i < capturedFrames.Count; i++)
            captures[i] = System.Convert.ToBase64String(capturedFrames[i]);

        // Build payload
        var payload = new Payload
        {
            businessName = businessName,
            room = new RoomData { anchors = anchorList.ToArray() },
            captures = captures
        };

        string json = JsonUtility.ToJson(payload);
        Debug.Log($"[ApiClient] Sending: {json.Length} chars, {captures.Length} images");

        // POST
        string endpoint = $"{apiUrl.TrimEnd('/')}/receive-data";
        try
        {
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
                    Debug.Log($"[ApiClient] Response: {req.downloadHandler.text}");
                    return ParseResponse(req.downloadHandler.text);
                }
                else
                {
                    Debug.LogError($"[ApiClient] POST failed: {req.error} — {req.downloadHandler.text}");
                    return null;
                }
            }
        }
        catch (System.Exception e)
        {
            Debug.LogError($"[ApiClient] Exception: {e}");
            return null;
        }
    }

    private static float[] ToArray(Vector3 v) => new float[] { v.x, v.y, v.z };
    private static float[] ToArray(Quaternion q) => new float[] { q.x, q.y, q.z, q.w };

    /// <summary>
    /// The backend returns a raw JSON array of Conclusion objects (one per batch).
    /// JsonUtility can't parse a top-level array, so wrap it in an object first.
    /// Falls back to treating the body as a single Conclusion if it isn't an array.
    /// </summary>
    private static ApiResponse ParseResponse(string json)
    {
        string trimmed = json.TrimStart();
        if (trimmed.StartsWith("["))
        {
            return JsonUtility.FromJson<ApiResponse>("{\"conclusions\":" + json + "}");
        }
        if (trimmed.StartsWith("{"))
        {
            var single = JsonUtility.FromJson<Conclusion>(json);
            return new ApiResponse { conclusions = single != null ? new[] { single } : null };
        }
        Debug.LogError("[ApiClient] Unexpected response body, not JSON object or array.");
        return null;
    }
}
