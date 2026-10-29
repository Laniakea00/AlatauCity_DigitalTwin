using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Ai
{
    /// <summary>The function-calling loop with the AI proxy (coroutine, UnityWebRequest — no threads, works in WebGL):
    /// the question goes to the proxy → the model asks for functions → the twin runs them on its own data (AiTools) → the results go
    /// back → the model answers. The model's turns are sent back verbatim (they carry its thought signatures).</summary>
    public static class AiClient
    {
        public const int MaxRounds = 4;

        public class Result
        {
            public string Text, Model, Error;
            public AiTools.Turn Turn = new AiTools.Turn();
            public bool Ok => Error == null && !string.IsNullOrEmpty(Text);
        }

        /// <summary>A short memory of the last exchanges (plain text), so «а в 2040?» works after a question about population.</summary>
        static readonly List<(string q, string a)> history = new List<(string, string)>();
        public static void Remember(string q, string a) { history.Add((q, a)); while (history.Count > 2) history.RemoveAt(0); }

        public static IEnumerator Ask(string question, string lang, Action<Result> done)
        {
            var res = new Result();
            var contents = new List<object>();
            foreach (var (hq, ha) in history)
            {
                contents.Add(AiJson.O("role", "user", "parts", AiJson.A(AiJson.O("text", hq))));
                contents.Add(AiJson.O("role", "model", "parts", AiJson.A(AiJson.O("text", ha))));
            }
            contents.Add(AiJson.O("role", "user", "parts", AiJson.A(AiJson.O("text", question.Length > 1500 ? question.Substring(0, 1500) : question))));
            var tools = new List<object>(); foreach (var n in AiTools.Names) tools.Add(n);

            for (int round = 0; round < MaxRounds; round++)
            {
                var body = AiJson.O("lang", lang, "model", string.IsNullOrEmpty(AiConfig.Model) ? null : AiConfig.Model, "contents", contents, "tools", tools);
                string text = null, err = null;
                using (var rq = new UnityWebRequest(AiConfig.ProxyUrl + "/chat", "POST"))
                {
                    rq.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(AiJson.Write(body)));
                    rq.downloadHandler = new DownloadHandlerBuffer();
                    rq.SetRequestHeader("Content-Type", "application/json");
                    rq.timeout = AiConfig.TimeoutS;
                    yield return rq.SendWebRequest();
                    if (rq.result != UnityWebRequest.Result.Success) err = rq.responseCode > 0 ? "HTTP " + rq.responseCode : rq.error;
                    else text = rq.downloadHandler.text;
                }
                if (err != null) { res.Error = err; break; }

                object o;
                try { o = TwinJson.Parse(text); } catch (Exception e) { res.Error = "bad reply: " + e.Message; break; }
                res.Model = TwinJson.S(TwinJson.G(o, "model"));
                var calls = TwinJson.A(TwinJson.G(o, "calls"));
                if (calls == null || calls.Count == 0)
                {
                    res.Text = TwinJson.S(TwinJson.G(o, "text")).Trim();
                    if (res.Text.Length == 0) res.Error = "empty answer";
                    break;
                }
                // the model's own turn goes back unchanged, then one turn with the results of all its calls
                contents.Add(new AiJson.Raw(TwinJson.S(TwinJson.G(o, "content"))));
                var parts = new List<object>();
                foreach (var c in calls)
                {
                    string name = TwinJson.S(TwinJson.G(c, "name"));
                    var args = TwinJson.O(TwinJson.G(c, "args")) ?? new Dictionary<string, object>();
                    var r = AiTools.Run(name, args, res.Turn);
                    var fr = AiJson.O("name", name, "response", r);
                    var id = TwinJson.G(c, "id") as string; if (!string.IsNullOrEmpty(id)) fr["id"] = id;
                    parts.Add(AiJson.O("functionResponse", fr));
                }
                contents.Add(AiJson.O("role", "user", "parts", parts));
                if (round == MaxRounds - 1) res.Error = "no answer after " + MaxRounds + " rounds";
            }
            if (res.Ok) Remember(question, res.Text);
            done(res);
        }
    }
}
