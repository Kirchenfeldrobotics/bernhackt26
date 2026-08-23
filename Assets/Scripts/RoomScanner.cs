using System.Collections.Generic;
using Meta.XR.MRUtilityKit;
using UnityEngine;

/// <summary>
/// Handles room scanning via MRUK and segments the floor into capture cells.
/// All segmentation settings are editable in the Inspector.
/// </summary>
public class RoomScanner : MonoBehaviour
{
    [Header("Segmentation")]
    [SerializeField] private float segmentSize = 2.2f;
    [SerializeField] private float personRadius = 0.25f;
    [SerializeField] private float minFreeFloorRatio = 0.20f;
    [SerializeField] private float floorObstacleMaxHeight = 0.30f;
    [SerializeField] private int floorSamplesPerAxis = 5;

    [Header("Depth")]
    [SerializeField] private float minCaptureDepth = 3.0f;

    /// <summary>
    /// A single cell on the floor grid that needs a photo capture.
    /// </summary>
    public class CaptureCell
    {
        public int gridX, gridZ;
        public Vector3 worldCenter;
        public Vector3 standPoint;
        public float freeRatio;
        public bool captured;

        // Aiming — solved at runtime by CaptureGuide
        public Vector3 aimDirection;
        public float requiredDepth;
        public bool aimRelaxed;
        public Vector3 aimAnchor;
        public bool aimSolved;
    }

    public List<CaptureCell> Cells { get; private set; } = new List<CaptureCell>();
    public Vector3 RoomCentroid { get; private set; }
    public float MinCaptureDepth => minCaptureDepth;
    public bool HasRoom { get; private set; }

    private readonly List<MRUKAnchor> floorObstacles = new List<MRUKAnchor>();
    private readonly List<Vector3> freeSamples = new List<Vector3>();

    private const MRUKAnchor.SceneLabels StructureLabels =
        MRUKAnchor.SceneLabels.FLOOR | MRUKAnchor.SceneLabels.CEILING |
        MRUKAnchor.SceneLabels.WALL_FACE | MRUKAnchor.SceneLabels.INVISIBLE_WALL_FACE |
        MRUKAnchor.SceneLabels.INNER_WALL_FACE | MRUKAnchor.SceneLabels.GLOBAL_MESH |
        MRUKAnchor.SceneLabels.DOOR_FRAME | MRUKAnchor.SceneLabels.WINDOW_FRAME |
        MRUKAnchor.SceneLabels.WALL_ART;

    /// <summary>
    /// Tries to load an existing room scan. Returns true if a room was found.
    /// </summary>
    public async System.Threading.Tasks.Task<bool> TryLoadExistingRoom()
    {
        var result = await MRUK.Instance.LoadSceneFromDevice(requestSceneCaptureIfNoDataFound: false);
        Debug.Log($"[RoomScanner] Load result: {result}");

        var room = MRUK.Instance.GetCurrentRoom();
        HasRoom = room != null && room.Anchors.Count > 0;
        Debug.Log($"[RoomScanner] HasRoom={HasRoom}, anchors={room?.Anchors.Count ?? 0}");
        return HasRoom;
    }

    /// <summary>
    /// Launches Meta Space Setup for the user to scan their room.
    /// Returns true if a valid room scan was obtained.
    /// </summary>
    public async System.Threading.Tasks.Task<bool> StartRoomScan()
    {
        Debug.Log("[RoomScanner] Launching Space Setup...");
        var result = await MRUK.Instance.LoadSceneFromDevice(requestSceneCaptureIfNoDataFound: true);
        Debug.Log($"[RoomScanner] Scan result: {result}");

        var room = MRUK.Instance.GetCurrentRoom();
        HasRoom = room != null && room.Anchors.Count > 0;
        return HasRoom;
    }

    /// <summary>
    /// Segments the room floor into a grid of standable cells.
    /// Call this after a successful room scan.
    /// </summary>
    public void SegmentRoom()
    {
        Cells.Clear();
        MRUKRoom room = MRUK.Instance.GetCurrentRoom();
        if (room == null) { Debug.LogError("[RoomScanner] No room!"); return; }

        Bounds bounds = room.GetRoomBounds();
        Vector3 min = bounds.min;
        Vector3 max = bounds.max;

        int gridCountX = Mathf.CeilToInt((max.x - min.x) / segmentSize);
        int gridCountZ = Mathf.CeilToInt((max.z - min.z) / segmentSize);

        float floorY = (room.FloorAnchors != null && room.FloorAnchors.Count > 0)
            ? room.FloorAnchors[0].transform.position.y
            : min.y;

        CollectFloorObstacles(room, floorY);

        for (int gx = 0; gx < gridCountX; gx++)
        {
            for (int gz = 0; gz < gridCountZ; gz++)
            {
                Vector3 center = new Vector3(
                    min.x + (gx + 0.5f) * segmentSize,
                    floorY + 0.05f,
                    min.z + (gz + 0.5f) * segmentSize
                );

                float freeRatio = MeasureCellFloor(room, center, out Vector3 standPoint, out float inRoomRatio);

                if (inRoomRatio <= 0f) continue;
                if (freeRatio <= 0f) continue;
                if (freeRatio < minFreeFloorRatio) continue;

                Cells.Add(new CaptureCell
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

        // Compute centroid of all stand points
        RoomCentroid = Vector3.zero;
        foreach (var c in Cells) RoomCentroid += c.standPoint;
        if (Cells.Count > 0) RoomCentroid /= Cells.Count;

        Debug.Log($"[RoomScanner] {Cells.Count} standable cells, centroid={RoomCentroid}");
    }

    /// <summary>
    /// Finds which cell the player is currently standing in. Returns null if none.
    /// </summary>
    public CaptureCell FindCellAtPosition(Vector3 worldPos)
    {
        float half = segmentSize * 0.5f;
        foreach (var c in Cells)
        {
            if (Mathf.Abs(worldPos.x - c.worldCenter.x) <= half &&
                Mathf.Abs(worldPos.z - c.worldCenter.z) <= half)
                return c;
        }
        return null;
    }

    /// <summary>
    /// Measures depth (distance to nearest wall/surface) along a direction.
    /// </summary>
    public float MeasureDepthAhead(Vector3 origin, Vector3 direction)
    {
        MRUKRoom room = MRUK.Instance.GetCurrentRoom();
        if (room == null) return 0f;

        Ray ray = new Ray(origin, direction);
        const float maxDist = 20f;

        if (room.Raycast(ray, maxDist, out RaycastHit hit))
            return hit.distance;
        return maxDist;
    }

    /// <summary>
    /// Returns the current MRUK room, or null.
    /// </summary>
    public MRUKRoom GetCurrentRoom()
    {
        return MRUK.Instance?.GetCurrentRoom();
    }

    // --- Private helpers (from Nils' segmentation logic) ---

    private void CollectFloorObstacles(MRUKRoom room, float floorY)
    {
        floorObstacles.Clear();
        if (room.Anchors == null) return;

        foreach (MRUKAnchor a in room.Anchors)
        {
            if (a == null || !a.VolumeBounds.HasValue) continue;
            if ((a.Label & StructureLabels) != 0) continue;
            if (VolumeWorldMinY(a) > floorY + floorObstacleMaxHeight) continue;
            floorObstacles.Add(a);
        }
    }

    private static float VolumeWorldMinY(MRUKAnchor a)
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

    private bool IsBlockedByFurniture(Vector3 p)
    {
        foreach (MRUKAnchor a in floorObstacles)
            if (a.IsPositionInVolume(p, testVerticalBounds: false, personRadius * 2f))
                return true;
        return false;
    }

    private bool IsStandableFloor(MRUKRoom room, Vector3 p)
    {
        return room.IsPositionInRoom(p, testVerticalBounds: false) && !IsBlockedByFurniture(p);
    }

    private float MeasureCellFloor(MRUKRoom room, Vector3 center, out Vector3 standPoint, out float inRoomRatio)
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
}
