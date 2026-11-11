using UnityEngine;
namespace AlatauCity.DigitalTwin
{
    /// <summary>Merged building mesh. Triangle -> building id and opening year come from ChunkBake (the runs of triangles of one building,
    /// computed when the scene is built), so the render mesh keeps no copy in memory; the collider is a positions-only mesh with the
    /// same triangle order. Once, the film look gets which way each building is turned (_AlatauRoofTex, ChunkBake.ApplyRoofs): roof
    /// membranes, plant, solar rows and metal ribs drawn by AlatauFilm.cginc run along the building and not along the map grid.
    /// The mesh has two submeshes when AlatauRoofs put details on its roofs (parapets, crowns, plant, tile roofs): further than
    /// RoofDetailsTo from the camera those are under two pixels and only the bodies are drawn (one material instead of two).</summary>
    [RequireComponent(typeof(MeshFilter))]
    public class BuildingChunk : MonoBehaviour
    {
        string meshName;
        string MeshName { get { if (meshName == null) { var m = GetComponent<MeshFilter>().sharedMesh; meshName = m != null ? m.name : ""; } return meshName; } }
        public int BuildingAt(int triangle) => ChunkBake.BuildingAt(MeshName, triangle);
        public float YearAt(int triangle) => ChunkBake.YearAt(MeshName, triangle);

        /// <summary>m: roof details of a chunk are drawn while the camera is within this distance of the chunk's box (about 2 m per pixel
        /// at full HD there, a parapet or a roof unit is under two pixels beyond).</summary>
        public const float RoofDetailsTo = 3000f;
        MeshRenderer mr; Material[] both, bodies; bool near = true; int slot;
        static int count;

        void Start()
        {
            ChunkBake.ApplyRoofs();
            mr = GetComponent<MeshRenderer>(); var mf = GetComponent<MeshFilter>();
            if (mr == null || mf == null || mf.sharedMesh == null || mf.sharedMesh.subMeshCount < 2 || mr.sharedMaterials.Length < 2) { enabled = false; return; }
            both = mr.sharedMaterials; bodies = new[] { both[0] }; slot = count++ % 8;
        }

        void Update()
        {
            if ((Time.frameCount & 7) != slot) return;                     // one chunk in eight per frame: the switch is a distance band
            var cam = Camera.main; if (cam == null) return;
            bool n = mr.bounds.SqrDistance(cam.transform.position) < RoofDetailsTo * RoofDetailsTo;
            if (n == near) return;
            near = n; mr.sharedMaterials = n ? both : bodies;
        }
    }
}
