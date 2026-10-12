using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace AlatauCity.DigitalTwin.Data
{
    /// <summary>Files of StreamingAssets/twin. On desktop they are read from disk when asked; in a WebGL build the browser cannot
    /// read files, so all of them are downloaded once at start-up (UnityWebRequest) and served from memory.</summary>
    public static class TwinFiles
    {
        public static readonly string[] All = { "roads.json", "networks.json", "loads.json", "construction.json", "finance.json", "traffic.json",
                                                "scenarios.json", "risk.json", "gate_q1.json", "gate_q1.bytes" };
        static readonly Dictionary<string, byte[]> cache = new Dictionary<string, byte[]>();
        public static bool NeedsDownload => Application.platform == RuntimePlatform.WebGLPlayer;

        public static byte[] Bytes(string name)
        {
            if (cache.TryGetValue(name, out var b)) return b;
            return File.ReadAllBytes(Path.Combine(Application.streamingAssetsPath, "twin", name));
        }
        public static string Text(string name)
        {
            var b = Bytes(name); int o = b.Length >= 3 && b[0] == 0xEF && b[1] == 0xBB && b[2] == 0xBF ? 3 : 0;     // UTF-8 BOM
            return Encoding.UTF8.GetString(b, o, b.Length - o);
        }

        /// <summary>Downloads every file (WebGL); calls done(null) or done(error).</summary>
        public static IEnumerator Download(Action<string> done)
        {
            string err = null;
            foreach (var name in All)
            {
                var url = Application.streamingAssetsPath + "/twin/" + name;
                using (var rq = UnityWebRequest.Get(url))
                {
                    yield return rq.SendWebRequest();
                    if (rq.result != UnityWebRequest.Result.Success) { err = name + ": " + rq.error; Debug.LogError("[Alatau] " + url + ": " + rq.error); continue; }
                    cache[name] = rq.downloadHandler.data;
                }
            }
            done(err);
        }
    }
}
