using System.Collections;
using UnityEngine;
using UnityEngine.Networking;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Ai
{
    /// <summary>StreamingAssets/ai_config.json: { "proxyUrl": "", "model": "" }. An empty proxyUrl (the default) keeps the scripted
    /// assistant; a URL of the AI proxy (UnityProject/Tools/ai_proxy) turns on Gemini. The API key is never in the build — only the proxy has it.</summary>
    public static class AiConfig
    {
        public static string ProxyUrl = "";
        public static string Model = "";
        /// <summary>Seconds per request to the proxy; after it the scripted answer is shown.</summary>
        public const int TimeoutS = 15;
        public static bool Loaded { get; private set; }
        static bool loading;
        public static bool Online => Loaded && !string.IsNullOrEmpty(ProxyUrl);

        /// <summary>Reads the config once (UnityWebRequest works for StreamingAssets on desktop and in WebGL). A missing file = offline.</summary>
        public static IEnumerator Load()
        {
            if (Loaded || loading) yield break;
            loading = true;
            var path = Application.streamingAssetsPath + "/ai_config.json";
            if (!path.Contains("://")) path = "file://" + path;
            using (var rq = UnityWebRequest.Get(path))
            {
                rq.timeout = 5;
                yield return rq.SendWebRequest();
                if (rq.result == UnityWebRequest.Result.Success)
                {
                    try
                    {
                        var o = TwinJson.Parse(rq.downloadHandler.text);
                        ProxyUrl = TwinJson.S(TwinJson.G(o, "proxyUrl")).Trim().TrimEnd('/');
                        Model = TwinJson.S(TwinJson.G(o, "model")).Trim();
                    }
                    catch (System.Exception e) { Debug.LogWarning("[Alatau] ai_config.json: " + e.Message); ProxyUrl = ""; }
                }
            }
            Loaded = true; loading = false;
        }
    }
}
