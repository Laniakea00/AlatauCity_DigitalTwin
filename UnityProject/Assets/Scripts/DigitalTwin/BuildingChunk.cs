using UnityEngine;
namespace AlatauCity.DigitalTwin
{
    /// <summary>Merged building mesh. Triangle -> building id is read from uv2.y of the (unwelded) triangle.</summary>
    [RequireComponent(typeof(MeshFilter))]
    public class BuildingChunk : MonoBehaviour
    {
        Vector2[] info;
        public int BuildingAt(int triangle)
        {
            if (info == null) { var m = GetComponent<MeshFilter>().sharedMesh; if (m == null || !m.isReadable) return -1; var l = new System.Collections.Generic.List<Vector2>(); m.GetUVs(1, l); info = l.ToArray(); }
            int v = triangle * 3; if (triangle < 0 || v >= info.Length) return -1;
            return Mathf.RoundToInt(info[v].y) - 1;
        }
        public float YearAt(int triangle) { BuildingAt(0); int v = triangle * 3; return info != null && v >= 0 && v < info.Length ? info[v].x : 0; }
    }
}
