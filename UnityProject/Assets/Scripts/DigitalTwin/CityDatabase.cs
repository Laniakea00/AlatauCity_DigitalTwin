using System.Collections.Generic;
using System.Globalization;
using UnityEngine;
namespace AlatauCity.DigitalTwin
{
    /// <summary>All building passports (57,690). CityDatabase.Instance.Buildings[bid]; ById["GATE_tower_2031_01234"].</summary>
    [DefaultExecutionOrder(-100)]
    public class CityDatabase : MonoBehaviour
    {
        public TextAsset buildings;           // buildings.csv
        public static CityDatabase Instance;
        public BuildingInfo[] Buildings = new BuildingInfo[0];
        public Dictionary<string, BuildingInfo> ById = new Dictionary<string, BuildingInfo>();
        public double eastingOffset = 663000, northingOffset = 4830000;
        void Awake() { Instance = this; Load(); }
        static float F(string s) => float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0f;
        static int I(string s) => int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out var v) ? v : 0;
        static double D(string s) => double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0;
        public void Load()
        {
            if (buildings == null) return;
            var lines = buildings.text.Split('\n'); var list = new List<BuildingInfo>(lines.Length);
            // bid,id,district,kind,use,source,year,floors,height_m,gfa_m2,parcel,x,z,ground_m,easting,northing
            for (int i = 1; i < lines.Length; i++)
            {
                var l = lines[i].Trim(); if (l.Length == 0) continue; var p = l.Split(','); if (p.Length < 16) continue;
                var b = new BuildingInfo { Bid = I(p[0]), Id = p[1], District = p[2], Kind = p[3], Use = p[4], Source = p[5], Year = I(p[6]), Floors = I(p[7]),
                    HeightM = F(p[8]), GfaM2 = F(p[9]), Parcel = p[10], X = F(p[11]), Z = F(p[12]), GroundM = F(p[13]), Easting = D(p[14]), Northing = D(p[15]),
                    Status = p[5] == "existing_osm" ? "existing" : "planned" };
                list.Add(b); ById[b.Id] = b;
            }
            list.Sort((a, c) => a.Bid.CompareTo(c.Bid));
            Buildings = list.ToArray();
            Debug.Log($"[Alatau] CityDatabase: {Buildings.Length} buildings");
            CityStats.Rebuild(TwinState.Scenario); TwinScenario.Apply(TwinState.Scenario);
        }
        public BuildingInfo Get(int bid) => bid >= 0 && bid < Buildings.Length && Buildings[bid].Bid == bid ? Buildings[bid] : null;
        /// <summary>UTM 43N (EPSG:32643) -> Unity world position.</summary>
        public Vector3 FromUtm(double easting, double northing, double elevation) => new Vector3((float)(easting - eastingOffset), (float)elevation, (float)(northing - northingOffset));
    }
}
