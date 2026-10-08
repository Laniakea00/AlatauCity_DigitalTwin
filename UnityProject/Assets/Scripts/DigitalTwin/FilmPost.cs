using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Picture finish of the film look, on the main camera: soft shading where surfaces meet (ambient occlusion from depth),
    /// a gentle depth of field around what the camera looks at, bloom, and the grade (exposure, soft highlights, contrast, vignette).
    /// The interface is drawn after this and is not affected. Added and switched by FilmLook.</summary>
    [RequireComponent(typeof(Camera))]
    public class FilmPost : MonoBehaviour
    {
        [Range(0, 2)] public float aoStrength = 1.25f;
        public float aoRadius = 14f;                     // metres; FilmLook sets it from the camera distance
        public bool depthOfField = true;
        public float focus = 2000f, focusRange = 1200f;  // metres; FilmLook follows the camera target
        [Range(0, 12)] public float maxBlur = 5f;        // pixels at 1080 lines
        [Range(0, 1)] public float bloom = 0.32f;
        [Range(0.5f, 1.2f)] public float bloomThreshold = 0.86f;
        [Range(0.5f, 2)] public float exposure = 1.06f;
        [Range(0.8f, 1.4f)] public float contrast = 1.10f;
        [Range(0, 1.6f)] public float saturation = 1.04f;
        [Range(0, 1)] public float vignette = 0.30f;

        Camera cam; Material mat; bool hdr0; DepthTextureMode depth0;
        static readonly int ProjId = Shader.PropertyToID("_Proj"), FadeId = Shader.PropertyToID("_Fade"), GradeId = Shader.PropertyToID("_Grade"), BloomPId = Shader.PropertyToID("_BloomP"),
            DirId = Shader.PropertyToID("_Dir"), DofId = Shader.PropertyToID("_Dof"), AoTexId = Shader.PropertyToID("_AoTex"), BloomTexId = Shader.PropertyToID("_BloomTex"), AddTexId = Shader.PropertyToID("_AddTex");

        void OnEnable()
        {
            cam = GetComponent<Camera>(); hdr0 = cam.allowHDR; depth0 = cam.depthTextureMode;
            cam.depthTextureMode |= DepthTextureMode.Depth; cam.allowHDR = true;
            if (mat == null) { var sh = Shader.Find("Hidden/AlatauCity/FilmPost"); if (sh != null) mat = new Material(sh) { hideFlags = HideFlags.HideAndDontSave }; }
        }

        void OnDisable() { if (cam != null) { cam.allowHDR = hdr0; cam.depthTextureMode = depth0; } }

        void OnRenderImage(RenderTexture src, RenderTexture dst)
        {
            if (mat == null) { Graphics.Blit(src, dst); return; }
            int w = src.width, h = src.height; var P = cam.projectionMatrix;
            mat.SetVector(ProjId, new Vector4(1f / P.m00, 1f / P.m11, aoRadius, aoStrength));
            mat.SetVector(FadeId, new Vector4(RenderSettings.fog ? RenderSettings.fogDensity : 0f, Time.frameCount % 64, 0, 0));
            mat.SetVector(GradeId, new Vector4(exposure, contrast, saturation, vignette));
            mat.SetVector(BloomPId, new Vector4(bloomThreshold, bloom, 0, 0));
            mat.SetVector(DofId, new Vector4(focus, focusRange, maxBlur * h / 1080f, depthOfField ? 1f : 0f));

            // 1. ambient occlusion at half size, blurred along the surfaces
            var ao = RenderTexture.GetTemporary(w / 2, h / 2, 0, RenderTextureFormat.R8); var ao2 = RenderTexture.GetTemporary(w / 2, h / 2, 0, RenderTextureFormat.R8);
            Graphics.Blit(src, ao, mat, 0);
            mat.SetVector(DirId, new Vector4(2f / w, 0, 0, 0)); Graphics.Blit(ao, ao2, mat, 1);
            mat.SetVector(DirId, new Vector4(0, 2f / h, 0, 0)); Graphics.Blit(ao2, ao, mat, 1);
            var a = RenderTexture.GetTemporary(w, h, 0, RenderTextureFormat.DefaultHDR); var b = RenderTexture.GetTemporary(w, h, 0, RenderTextureFormat.DefaultHDR);
            mat.SetTexture(AoTexId, ao); Graphics.Blit(src, a, mat, 2);
            // 2. depth of field
            Graphics.Blit(a, b, mat, 3);
            // 3. bloom: bright parts, four sizes down, then back up
            const int N = 4; var down = new RenderTexture[N];
            int bw = w / 2, bh = h / 2;
            down[0] = RenderTexture.GetTemporary(bw, bh, 0, RenderTextureFormat.DefaultHDR); Graphics.Blit(b, down[0], mat, 4);
            for (int i = 1; i < N; i++) { bw = Mathf.Max(2, bw / 2); bh = Mathf.Max(2, bh / 2); down[i] = RenderTexture.GetTemporary(bw, bh, 0, RenderTextureFormat.DefaultHDR); Graphics.Blit(down[i - 1], down[i], mat, 5); }
            var up = down[N - 1];
            for (int i = N - 2; i >= 0; i--)
            {
                var t = RenderTexture.GetTemporary(down[i].width, down[i].height, 0, RenderTextureFormat.DefaultHDR);
                mat.SetTexture(AddTexId, down[i]); Graphics.Blit(up, t, mat, 6);
                if (up != down[N - 1]) RenderTexture.ReleaseTemporary(up);
                up = t;
            }
            // 4. the grade
            mat.SetTexture(BloomTexId, up); Graphics.Blit(b, dst, mat, 7);
            if (up != down[N - 1]) RenderTexture.ReleaseTemporary(up);
            for (int i = 0; i < N; i++) RenderTexture.ReleaseTemporary(down[i]);
            RenderTexture.ReleaseTemporary(ao); RenderTexture.ReleaseTemporary(ao2); RenderTexture.ReleaseTemporary(a); RenderTexture.ReleaseTemporary(b);
        }
    }
}
