using UnityEngine;
namespace AlatauCity.DigitalTwin
{
    /// <summary>Merged building mesh. Triangle -> building id and opening year come from ChunkBake (the runs of triangles of one building,
    /// computed when the scene is built), so the render mesh keeps no copy in memory; the collider is a positions-only mesh with the
    /// same triangle order. Once, the film look gets which way each building is turned (_AlatauRoofTex, ChunkBake.ApplyRoofs): roof
    /// membranes, plant, solar rows and metal ribs drawn by AlatauFilm.cginc run along the building and not along the map grid.</summary>
    [RequireComponent(typeof(MeshFilter))]
    public class BuildingChunk : MonoBehaviour
    {
        string meshName;
        string MeshName { get { if (meshName == null) { var m = GetComponent<MeshFilter>().sharedMesh; meshName = m != null ? m.name : ""; } return meshName; } }
        public int BuildingAt(int triangle) => ChunkBake.BuildingAt(MeshName, triangle);
        public float YearAt(int triangle) => ChunkBake.YearAt(MeshName, triangle);

        void Start() { ChunkBake.ApplyRoofs(); enabled = false; }
    }
}
