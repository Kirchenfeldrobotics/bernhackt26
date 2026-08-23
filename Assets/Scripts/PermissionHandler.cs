using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Android;

/// <summary>
/// Handles Android permission requests for Scene and Camera access.
/// Attach to any GameObject — no Inspector config needed.
/// </summary>
public class PermissionHandler : MonoBehaviour
{
    /// <summary>
    /// Requests a single Android permission and waits for the user's answer.
    /// Returns true if granted.
    /// </summary>
    public async Task<bool> EnsurePermission(string permission, string friendlyName)
    {
        if (Permission.HasUserAuthorizedPermission(permission))
        {
            Debug.Log($"[Permissions] Already granted: {friendlyName}");
            return true;
        }

        Debug.Log($"[Permissions] Requesting: {friendlyName} ({permission})");

        bool answered = false, granted = false;
        var cb = new PermissionCallbacks();
        cb.PermissionGranted += _ => { granted = true; answered = true; };
        cb.PermissionDenied += _ => { granted = false; answered = true; };
        Permission.RequestUserPermission(permission, cb);

        float deadline = Time.unscaledTime + 180f;
        while (!answered && Time.unscaledTime < deadline)
        {
            if (Permission.HasUserAuthorizedPermission(permission)) { granted = true; break; }
            await Task.Yield();
        }

        if (!granted)
            granted = Permission.HasUserAuthorizedPermission(permission);

        Debug.Log($"[Permissions] {friendlyName} granted={granted}");
        return granted;
    }

    /// <summary>
    /// Requests both Scene and Camera permissions. Returns true only if both are granted.
    /// </summary>
    public async Task<bool> RequestAllPermissions()
    {
        bool scene = await EnsurePermission(
            OVRPermissionsRequester.ScenePermission,
            "Scene / spatial data"
        );
        if (!scene) return false;

        bool camera = await EnsurePermission(
            OVRPermissionsRequester.PassthroughCameraAccessPermission,
            "Headset camera"
        );
        return camera;
    }
}
