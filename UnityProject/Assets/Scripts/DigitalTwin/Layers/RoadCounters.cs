using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Run counters of the road package, written to the log every 10 s of play (unscaled time) and once when play stops:
    ///   [Alatau] counters cars_off=… people_off=… cars=… people=… ramp_cars=… ramp_in=… raised_cars=… park_people=… park_off=… year=… sc=… t=…s
    /// cars_off = cars of the film traffic that are not on a drawn carriageway or junction patch at its height (the Gate district's own
    /// streets are not counted); people_off = street people of the film life not on a pavement, pedestrian street or bike path;
    /// ramp_cars = cars on a ramp of the redrawn map now, ramp_in = cars that turned on to one since the start; raised_cars = cars on a
    /// road that leaves the terrain somewhere (decks, embankments); park_people = people on the park walks (map_walks.json), park_off = those
    /// of them standing where the ground drawn is not paved (on the grass beside a walk). One pass over the live cars and the people drawn in the last frame,
    /// every 10 s only: no per-frame work, no allocation but the log line.
    /// Street furniture (rule 20: a lamp, signal or sign on a carriageway or inside a building is an error), per district of
    /// districts.json, once the lamps are placed and again whenever the signal posts are placed anew (year, scenario, the Gate district):
    ///   [Alatau] street furniture 2050 sc0: Gate lamps N (a on a carriageway, b inside a building) signals M (a, b) signs K (a, b); Golden …
    /// The lamps are checked a slice per frame after their placement (a carriageway: FilmRoads.OnSurface; a building: a ray from above
    /// hits a building chunk whose building stands in the year shown). Signs are FilmTraffic's give-way and main-road signs at the
    /// junctions without lights (FilmSignals.SignGiveWay, SignPriority), checked as the signal posts.</summary>
    public class RoadCounters : MonoBehaviour
    {
        public static RoadCounters Instance;
        const float Every = 10f;
        float next = Every; bool stopped;
        // street furniture: per lamp its district (−1 outside), on a carriageway, the year of the building it stands in (0 none)
        sbyte[] lampD; bool[] lampCar; float[] lampB; int lampsSeen = -1, lampsDone, sigSeen = -1, furnYear = -1, furnSc = -1; float sigAt;
        readonly System.Collections.Generic.Dictionary<long, sbyte> distCell = new System.Collections.Generic.Dictionary<long, sbyte>();
        const int LampSlice = 2000;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Road counters").AddComponent<RoadCounters>(); }
        void Awake() { Instance = this; }

        void Update()
        {
            Furniture();
            if (Time.unscaledTime < next) return;
            next = Time.unscaledTime + Every;
            Log();
        }

        void OnApplicationQuit() { if (!stopped) { stopped = true; Log(); } }
        void OnDisable() { if (!stopped) { stopped = true; Log(); } }

        /// <summary>The counters now (also for the capture tools).</summary>
        public static void Count(out int cars, out int carsOff, out int people, out int peopleOff, out int rampCars, out int raised)
        {
            cars = carsOff = people = peopleOff = rampCars = raised = 0;
            if (FilmTraffic.Instance != null) FilmTraffic.Instance.Counters(out cars, out carsOff, out rampCars, out raised);
            if (FilmLife.Instance != null) FilmLife.Instance.Counters(out people, out peopleOff);
        }

        // ------------------------------------------------------------------ street furniture per district
        sbyte District(float x, float z)
        {
            long k = ((long)Mathf.FloorToInt(x / 100f) << 32) ^ (uint)Mathf.FloorToInt(z / 100f);
            if (!distCell.TryGetValue(k, out var d)) distCell[k] = d = (sbyte)CityStats.DistrictAt((Mathf.Floor(x / 100f) + 0.5f) * 100f, (Mathf.Floor(z / 100f) + 0.5f) * 100f);
            return d;
        }
        /// <summary>The year of the building whose footprint holds p (a ray from above hits its chunk first), 0 when none.</summary>
        static float BuildingOver(Vector3 p)
        {
            if (!Physics.Raycast(new Vector3(p.x, p.y + 400f, p.z), Vector3.down, out var hit, 399f, ~0, QueryTriggerInteraction.Ignore)) return 0f;
            if (hit.point.y < p.y + 1.5f) return 0f;                              // the ground, a deck, a kerb: nothing over the foot
            var ch = hit.collider.GetComponent<BuildingChunk>(); if (ch == null) return 0f;
            float y = ch.YearAt(hit.triangleIndex); return y > 0f ? y : 1f;
        }
        static bool OnCarriage(Vector3 p) => FilmRoads.OnSurface(p + new Vector3(0f, 0.1f, 0f), -0.3f, true);
        /// <summary>Rule 20 for one post whose foot is p (a lamp: FilmLamps.Foot; a signal post or a Gate district lamp: FilmSignals.Item.P):
        /// on a drawn carriageway or junction patch (of any year), or inside the footprint of a building (of any year). The lamps and the
        /// signal posts are placed by it, so the count below, made with the same two tests, finds none in any year.</summary>
        public static bool Blocked(Vector3 p) => OnCarriage(p) || BuildingOver(p) > 0f;
        void Furniture()
        {
            int n = FilmLamps.Count;
            if (FilmLamps.Placed != lampsSeen && n > 0)
            {
                lampsSeen = FilmLamps.Placed; lampsDone = 0; lampD = new sbyte[n]; lampCar = new bool[n]; lampB = new float[n]; furnYear = -1;
            }
            if (lampD == null || lampD.Length != n) return;
            if (lampsDone < n)
            {
                int end = Mathf.Min(n, lampsDone + LampSlice);
                for (int i = lampsDone; i < end; i++)
                {
                    FilmLamps.Foot(i, out var p, out _);
                    lampD[i] = District(p.x, p.z); lampCar[i] = OnCarriage(p); lampB[i] = BuildingOver(p);
                }
                lampsDone = end; return;
            }
            int year = TwinState.Year < 1 ? 2050 : TwinState.Year, sc = Mathf.Clamp((int)TwinState.Scenario, 0, 3);
            if (FilmSignals.Version != sigSeen) { sigSeen = FilmSignals.Version; sigAt = Time.unscaledTime; furnYear = -1; }
            if (furnYear == year && furnSc == sc) return;
            if (Time.unscaledTime - sigAt < 3f || FilmSignals.Items.Count == 0) return;      // the posts of a new year are still being placed
            furnYear = year; furnSc = sc;
            const int D = CityStats.Districts + 1;                                 // the four districts and «outside»
            var lamps = new int[D]; var lampsCar = new int[D]; var lampsIn = new int[D]; var sig = new int[D]; var sigCar = new int[D]; var sigIn = new int[D];
            var sign = new int[D]; var signCar = new int[D]; var signIn = new int[D];
            for (int i = 0; i < n; i++)
            {
                FilmLamps.Foot(i, out _, out var yv); if (yv[sc] > year) continue;
                int d = lampD[i] < 0 ? D - 1 : lampD[i]; lamps[d]++; if (lampCar[i]) lampsCar[d]++; if (lampB[i] > 0f && lampB[i] <= year) lampsIn[d]++;
            }
            foreach (var it in FilmSignals.Items)
            {
                int dd = District(it.P.x, it.P.z); int d = dd < 0 ? D - 1 : dd; float b = BuildingOver(it.P); bool car = OnCarriage(it.P);
                if (it.Type == 2) { lamps[d]++; if (car) lampsCar[d]++; if (b > 0f && b <= year) lampsIn[d]++; }   // the Gate district's own lamps
                else if (it.Type >= FilmSignals.SignGiveWay) { sign[d]++; if (car) signCar[d]++; if (b > 0f && b <= year) signIn[d]++; }
                else { sig[d]++; if (car) sigCar[d]++; if (b > 0f && b <= year) sigIn[d]++; }
            }
            var sb = new System.Text.StringBuilder($"[Alatau] street furniture {year} sc{sc}: ");
            for (int d = 0; d < D; d++)
                sb.Append(d < D - 1 ? CityStats.DistrictIds[d] : "outside the districts").Append($" lamps {lamps[d]} ({lampsCar[d]} on a carriageway, {lampsIn[d]} inside a building)")
                  .Append($" signals {sig[d]} ({sigCar[d]}, {sigIn[d]}) signs {sign[d]} ({signCar[d]}, {signIn[d]})").Append(d < D - 1 ? "; " : "");
            Debug.Log(sb.ToString());
        }

        static void Log()
        {
            Count(out int cars, out int carsOff, out int people, out int peopleOff, out int rampCars, out int raised);
            int parkPeople = 0, parkOff = 0;
            if (FilmLife.Instance != null) FilmLife.Instance.Counters(out _, out _, out parkPeople, out parkOff);
            Debug.Log($"[Alatau] counters cars_off={carsOff} people_off={peopleOff} cars={cars} people={people} ramp_cars={rampCars} " +
                      $"ramp_in={FilmTraffic.RampEntries} raised_cars={raised} park_people={parkPeople} park_off={parkOff} year={TwinState.Year} sc={(int)TwinState.Scenario} t={Time.unscaledTime:0}s");
        }
    }
}
