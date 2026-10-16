using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Procedural models of the landmarks. Local frame: x = long side, z = across, y = up from the base (0 = ground).
    /// Proportions follow the published figures (heights, areas, capacities); details are illustrative, not design documentation.</summary>
    /// <summary>The order in which each building of a complex is put up: stage windows in the progress of the building (0 … 1), shared
    /// by the model (LandmarkKit.Win: what rises when) and by the construction monitoring (the works of the schedule).</summary>
    public static class Wbs
    {
        static Vector2 V(float a, float b) => new Vector2(a, b);
        // Iconic Complex · hotel T2: excavation and raft, frame stepping up with the core, terraces (waterproofing and gardens), cascade
        public static readonly Vector2 T2Pit = V(0f, 0.08f), T2Frame = V(0.06f, 0.92f), T2Terr = V(0.55f, 0.88f), T2Cascade = V(0.62f, 0.90f);
        // retail blocks: the high block first, the low one a little later, the roof pool, the roof garden
        public static readonly Vector2 RHigh = V(0.08f, 0.85f), RLow = V(0.15f, 0.88f), RPool = V(0.70f, 0.92f), RGarden = V(0.75f, 0.95f);
        // grounds: the promenade, the allée with the fountain, the parterre and the square, trees and lamps
        public static readonly Vector2 GProm = V(0.15f, 0.65f), GAllee = V(0.30f, 0.80f), GSquare = V(0.35f, 0.85f), GTrees = V(0.65f, 1f);
        // KAIST · main hall: apron, columns of the lobby, transfer slab at +10 m, the steel box, its white grid, roof and pyramids,
        // the glazed lobby, terrace with stair and ramp, the plaza with the pool
        public static readonly Vector2 MApron = V(0f, 1f), MCols = V(0.10f, 0.30f), MSlab = V(0.26f, 0.40f), MBox = V(0.36f, 0.86f), MGrid = V(0.50f, 0.84f),
            MRoof = V(0.60f, 0.78f), MLobby = V(0.62f, 0.90f), MTerr = V(0.70f, 0.90f), MPlaza = V(0.86f, 1f);
        // laboratories: the spine, then wings A, B, C one after another, the courts last
        public static readonly Vector2 LSpine = V(0.06f, 0.42f), LCourts = V(0.85f, 1f);
        public static readonly Vector2[] LWing = { V(0.22f, 0.55f), V(0.34f, 0.68f), V(0.46f, 0.80f) };
        // north block: four sectors (захватки) along the arc from the west, then the green roof
        public static readonly Vector2[] NSector = { V(0.06f, 0.56f), V(0.16f, 0.66f), V(0.26f, 0.76f), V(0.36f, 0.86f) };
        public static readonly Vector2 NRoof = V(0.78f, 0.94f);
        // sports: the stand, its canopy, the running track, the pitch
        public static readonly Vector2 SStand = V(0.15f, 0.55f), SCanopy = V(0.45f, 0.70f), STrack = V(0.50f, 0.85f), SPitch = V(0.70f, 1f);
        // the park: ground and lawn, the lake and the island, paths and the bridge, lamps and fountains, the trees
        public static readonly Vector2 PGround = V(-0.02f, 1f), PLake = V(0.10f, 0.55f), PPaths = V(0.35f, 0.80f), PLamps = V(0.60f, 0.95f), PTrees = V(0.70f, 1f);
        public static readonly Vector2 Apron = V(0f, 1f);
    }

    public static class LandmarkModels
    {
        static void W(LandmarkKit k, Vector2 w, float y0, float y1) => k.Win(w.x, w.y, y0, y1);
        // palette
        static readonly Color32 White = LM.C("#ecebe6"), Stone = LM.C("#d9d4ca"), Pave = LM.C("#c8c2b6"), PaveDark = LM.C("#a9a397"), Concrete = LM.C("#bcb7ae"),
            GlassBlue = LM.C("#1f3549"), GlassTeal = LM.C("#1d3b3d"), GlassWarm = LM.C("#2b2f33"), GlassDark = LM.C("#151d26"),
            MetalW = LM.C("#e3e5e7"), MetalG = LM.C("#b9bdc2"), MetalD = LM.C("#6c7279"), Steel = LM.C("#4d535a"), Roof = LM.C("#9c9c98"),
            Grass = LM.C("#5f7f47"), GrassDark = LM.C("#4b6a39"), Leaf = LM.C("#557a3e"), Leaf2 = LM.C("#6a8a45"), Water = LM.C("#1e3446"),
            Warm = LM.C("#ffd9a0"), Red = LM.C("#e0261b"), Orange = LM.C("#f39a2b"), Asph = LM.C("#5d5d5c"), Gravel = LM.C("#9b958a");

        public static Mesh Build(string model, float seed)
        {
            var k = new LandmarkKit();
            switch (model)
            {
                case "iconic": Iconic(k); break;
                case "hotel_l7": HotelL7(k); break;
                case "food_pepsico": FoodPlant(k, LM.C("#0a4fa3"), true); break;
                case "food_mars": FoodPlant(k, LM.C("#1d3f8f"), false); break;
                case "paper": PaperMill(k); break;
                case "packaging": Packaging(k); break;
                case "logistics_griffin": Logistics(k, 2, 300f, 110f); break;
                case "logistics_gtrans": Logistics(k, 1, 210f, 90f); break;
                case "rail_terminal": RailTerminal(k); break;
                case "substation": Substation(k); break;
                case "power": PowerPlant(k); break;
                case "campus": Campus(k); break;
                case "hospital": Hospital(k); break;
                case "kpark": KPark(k); break;
                case "marina": Marina(k); break;
                case "airport": Airport(k); break;
                default: k.Box(new Vector3(0, 10, 0), new Vector3(40, 20, 40), 0, White, LM.Solid, 3.5f, Roof, LM.Roof); break;
            }
            return k.ToMesh("Landmark " + model);
        }

        // ------------------------------------------------------------------ helpers
        static void Pad(LandmarkKit k, float w, float d, float r, Color32 top, int mat = LM.Paving)
        {
            // a plinth that is buried in the slope: the model always stands on level ground
            k.Prism(LandmarkKit.RoundRect(0, 0, w, d, r, 3), -16f, 0.3f, PaveDark, LM.Solid, 3f, top, mat);
        }
        static void Lawn(LandmarkKit k, float cx, float cz, float w, float d, float r = 4f) => k.Prism(LandmarkKit.RoundRect(cx, cz, w, d, r, 3), 0.3f, 0.55f, GrassDark, LM.Solid, 3f, Grass, LM.Plant);
        static void Trees(LandmarkKit k, float x0, float z0, float x1, float z1, float step, float h, float seed)
        {
            int i = 0;
            for (float x = x0; x <= x1 + 0.01f; x += step) for (float z = z0; z <= z1 + 0.01f; z += step)
            { float j = Mathf.Sin((x * 12.9898f + z * 78.233f + seed) * 0.1f) * 0.5f + 0.5f; k.Tree(new Vector3(x, 0.4f, z), h * (0.8f + 0.4f * j), (i++ & 1) == 0 ? Leaf : Leaf2, j + seed); }
        }
        static void Gable(LandmarkKit k, float cx, float cz, float w, float d, float eave, float rise, Color32 wall, int wallMat, Color32 roof, float yaw = 0f)
        {
            var fp = LandmarkKit.Rect(cx, cz, w, d, yaw);
            k.Prism(fp, 0.3f, eave, wall, wallMat, 4f, roof, -1);
            var ridge = LandmarkKit.Rect(cx, cz, w, 0.6f, yaw);
            k.Loft(fp, eave, ridge, eave + rise, roof, LM.Metal, 4f);
            k.Cap(ridge, eave + rise, true, roof, LM.Metal);
        }
        static void Truck(LandmarkKit k, Vector3 p, float yaw, Color32 trailer)
        {
            var r = Quaternion.Euler(0, yaw, 0);
            k.Box(p + r * new Vector3(-1.6f, 2.3f, 0), new Vector3(13.6f, 3.0f, 2.5f), yaw, trailer, LM.Metal, 3f, trailer, LM.Roof);
            k.Box(p + r * new Vector3(6.2f, 1.9f, 0), new Vector3(2.4f, 2.6f, 2.4f), yaw, White, LM.Solid, 3f, White, LM.Roof);
        }
        static void Cars(LandmarkKit k, float x0, float z0, int nx, int nz, float seed)
        {
            Color32[] cols = { LM.C("#e7e7e7"), LM.C("#2b2b2b"), LM.C("#7d8590"), LM.C("#9b2a24"), LM.C("#2f4f7a"), LM.C("#c9c9c9") };
            for (int i = 0; i < nx; i++) for (int j = 0; j < nz; j++)
            {
                float h = Mathf.Abs(Mathf.Sin((i * 7.1f + j * 13.3f + seed) * 1.7f)); if (h < 0.25f) continue;
                k.Box(new Vector3(x0 + i * 2.7f, 1.0f, z0 + j * 6.5f), new Vector3(1.9f, 1.4f, 4.4f), 0, cols[(int)(h * 97) % cols.Length], LM.Solid, 3f, cols[(int)(h * 53) % cols.Length], LM.Roof);
            }
        }
        static void Silos(LandmarkKit k, float x0, float z0, int n, float r, float h, Color32 col)
        {
            for (int i = 0; i < n; i++) k.Cylinder(new Vector3(x0 + i * (r * 2.3f), 0.3f, z0), r, h, 16, col, LM.Metal, 4f, col, LM.Metal, r * 0.5f);
        }

        // ------------------------------------------------------------------ Iconic Complex (SOM): two separate buildings and a garden between them —
        // the 272 m tower (offices, residences, amenities at the top) wrapped in golden floor plates that project past the glass and turn a
        // little from floor to floor, its top glowing; the 80 m hotel stepping down to the west in planted terraces with a timber-and-garden
        // cascade in its middle; two low retail blocks (up to 32 m) with sloping green roofs and a roof pool; the square with an amphitheatre.
        static readonly Color32 Gold = LM.C("#cf9f45"), GoldLight = LM.C("#f2cf7f"), Bronze = LM.C("#3b3125"), WarmGlass = LM.C("#4d3d2a"),
            CrownGlass = LM.C("#c99c55"), Timber = LM.C("#b9853f"), Fascia = LM.C("#efe9dc"), PoolTile = LM.C("#7fb8c4"), PoolWater = LM.C("#2f8fb0");
        static void Iconic(LandmarkKit k)
        {
            var shape = IconicShape.P; IconicShape.P = TowerProfile.Iconic;          // the tower's footprint is the one of its interior floors
            Pad(k, 270f, 200f, 22f, Pave);

            // ---- the tower: glass shell on the shared footprint (IconicShape, the interior floors fit it), a golden plate at every floor
            // (parts of the model = the buildings of LandmarkData's Iconic Complex, each staged on its own dates: 1 T1, 2 T2, 3 east retail,
            // 4 west retail, 5 the grounds; 0 the plot)
            k.Part = 1;
            float xr = IconicShape.Xr, cz0 = IconicShape.Cz, H = 272f, roof = IconicShape.Roof, fh = IconicShape.Fh, crownFrom = 214f;
            var prev = IconicShape.Ring(0.3f); float yp = 0.3f; int fl = 0;
            for (float y = 0.3f + fh; y <= roof + 0.01f; y += fh, fl++)
            {
                var r = IconicShape.Ring(y); bool crown = yp >= crownFrom;
                k.Loft(prev, yp, r, y, crown ? CrownGlass : Bronze, LM.Glass, fh);
                if (fl > 0) Plate(k, prev, yp, fl, crown);
                prev = r; yp = y;
            }
            Plate(k, prev, yp, fl, true);
            // crown: the lean continues as a glass blade to a ridge; mast and aircraft light
            float dTop = IconicShape.D0 * 0.72f;
            var ridge = LandmarkKit.Chamfer(xr - 1.2f, cz0, 2.4f, dTop * 0.55f, 0.5f);
            k.Loft(prev, yp, ridge, 264f, CrownGlass, LM.Glass, 2.2f);
            k.Cap(ridge, 264f, true, GoldLight, LM.Metal);
            k.Beam(new Vector3(xr - 1.2f, 263f, cz0), new Vector3(xr - 1.2f, H, cz0), 0.9f, 0.9f, MetalG, LM.Steel);
            k.Box(new Vector3(xr - 1.2f, H - 0.4f, cz0), new Vector3(1.4f, 0.8f, 1.4f), 0, Red, LM.Light, 1f, Red, LM.Light);
            // lobby canopy toward the square
            k.Box(new Vector3(xr - 30f, 6.3f, cz0 - IconicShape.D0 * 0.5f - 7f), new Vector3(30f, 0.7f, 14f), 0, Gold, LM.Solid, 1f, Fascia, LM.Roof);

            // ---- the hotel: 80 m, stepping down to the west, two wings with a planted cascade between them
            k.Part = 2;
            const float hx0 = -128f, hx1 = -32f, hz0 = 14f, hz1 = 74f, gap = 10f, top = 80f; const int NS = 18;
            float step = (top - 0.3f) / NS, gz0 = (hz0 + hz1 - gap) * 0.5f, gz1 = gz0 + gap;
            for (int s = 0; s < NS; s++)
            {
                float y0 = 0.3f + s * step, y1 = y0 + step, x0 = Mathf.Lerp(hx0, hx1 - 12f, s / (NS - 1f));
                foreach (var (z0, z1) in new[] { (hz0, gz0), (gz1, hz1) })
                {
                    k.Prism(LandmarkKit.Rect((x0 + hx1) * 0.5f, (z0 + z1) * 0.5f, hx1 - x0, z1 - z0), y0, y1 - 1.0f, WarmGlass, LM.Glass, 3.4f, Fascia, -1);
                    k.Prism(LandmarkKit.Rect((x0 + hx1) * 0.5f - 0.6f, (z0 + z1) * 0.5f, hx1 - x0 + 1.2f, z1 - z0 + 1.2f), y1 - 1.0f, y1, Fascia, LM.Solid, 1f, Stone, LM.Paving);
                    // planted edge of the terrace this step leaves open
                    if (s < NS - 1)
                    {
                        // terraces: waterproofed and planted once the frame is past them (the lower ones first)
                        float tx = x0 + 1.6f, tq = s / (NS - 1f);
                        k.Win(Mathf.Lerp(Wbs.T2Terr.x, Wbs.T2Terr.y - 0.1f, tq), Mathf.Lerp(Wbs.T2Terr.x + 0.1f, Wbs.T2Terr.y, tq), y1, y1 + 4f);
                        k.Prism(LandmarkKit.Rect(tx, (z0 + z1) * 0.5f, 2.2f, z1 - z0 - 1.5f), y1, y1 + 0.7f, Stone, LM.Solid, 1f, Grass, LM.Plant);
                        for (float z = z0 + 3f; z < z1 - 2f; z += 6.5f) k.Tree(new Vector3(tx, y1 + 0.7f, z), 2.6f + (s % 3) * 0.5f, (s & 1) == 0 ? Leaf : Leaf2, s * 0.37f + z * 0.05f);
                        k.NoWin();
                    }
                }
                // the cascade: a garden that steps down between the wings, framed by timber fins
                W(k, Wbs.T2Cascade, y0, y0 + 4.2f);
                k.Prism(LandmarkKit.Rect((x0 + hx1) * 0.5f - 3f, (gz0 + gz1) * 0.5f, hx1 - x0 - 6f, gap), y0, y0 + 0.8f, Stone, LM.Solid, 1f, Grass, LM.Plant);
                if (s % 2 == 0) k.Tree(new Vector3((x0 + hx1) * 0.5f, y0 + 0.8f, (gz0 + gz1) * 0.5f), 3.4f, Leaf2, s * 0.21f);
                k.NoWin();
                for (float x = x0 + 1f; x < hx1 - 3f; x += 2.4f)
                    foreach (float z in new[] { gz0 + 0.25f, gz1 - 0.25f })
                        k.Box(new Vector3(x, (y0 + y1) * 0.5f, z), new Vector3(0.18f, step, 0.5f), 0f, Timber, LM.Solid, 20f, Timber, LM.Solid);
            }
            k.Box(new Vector3(hx1 - 6f, top + 1.5f, (hz0 + hz1) * 0.5f), new Vector3(9f, 3f, 20f), 0, MetalG, LM.Metal, 3f, Roof, LM.Roof);

            // ---- two retail blocks (podiums) with roof terraces and pools, as on the SOM renders: glass walls under a golden fascia,
            // the south-east one steps down from 26 m to 14 m, the west one rises from 14 m to 22 m toward the garden
            // (each: the high block first, the low one a little later, then the roof pool and the roof garden — Wbs.R*)
            k.Part = 3;
            W(k, Wbs.RHigh, 0.3f, 27.1f); Podium(k, 6f, -84f, 78f, -12f, 26f);
            W(k, Wbs.RLow, 0.3f, 15.1f); Podium(k, 78f, -84f, 120f, -12f, 14f);
            W(k, Wbs.RPool, 26f, 29f); RoofPool(k, 42f, -48f, 50f, 15f, 26f, 0f);
            W(k, Wbs.RGarden, 14f, 19.5f); RoofGarden(k, 99f, -48f, 34f, 64f, 14f);
            k.Part = 4;
            W(k, Wbs.RHigh, 0.3f, 23.1f); Podium(k, -70f, -84f, -24f, -12f, 22f);
            W(k, Wbs.RLow, 0.3f, 15.1f); Podium(k, -120f, -84f, -70f, -12f, 14f);
            W(k, Wbs.RPool, 22f, 25f); RoofPool(k, -47f, -48f, 15f, 40f, 22f, 90f);
            W(k, Wbs.RGarden, 14f, 19.5f); RoofGarden(k, -95f, -48f, 42f, 64f, 14f);

            // ---- grounds: a promenade with a double alley of clipped trees all around the plot, a formal allée with a fountain between
            k.Part = 5;
            // the tower and the hotel, a parterre north of the tower and a square with a reflecting pool east of it
            var keepOff = new List<Rect>
            {
                new Rect(4f, 9f, 66f, 51f),            // tower with its plates
                new Rect(-122f, 12f, 92f, 64f),        // hotel
                new Rect(4f, -86f, 118f, 76f), new Rect(-122f, -86f, 100f, 76f),   // podiums
                new Rect(19f, -4f, 34f, 18f),          // lobby canopy
                new Rect(-33f, -33f, 46f, 26f),        // amphitheatre
            };
            Promenade(k, 270f, 200f, keepOff);
            // the allée between the tower and the hotel, from the square to the north promenade
            W(k, Wbs.GAllee, 0.3f, 2.3f);
            k.Prism(LandmarkKit.Rect(-13f, 44f, 7f, 80f), 0.3f, 0.38f, Stone, LM.Solid, 1f, Pave, LM.Paving);
            Lawn(k, -25.5f, 44f, 9f, 80f, 1.5f); Lawn(k, -0.5f, 44f, 6f, 80f, 1.5f);
            for (float z = 8f; z <= 82f; z += 8f)
            {
                if (Mathf.Abs(z - 44f) < 9f) continue;
                W(k, Wbs.GTrees, 0.3f, 9f); Planted(k, -19.5f, z, 7.5f, 0); Planted(k, -6.5f, z, 7.5f, 1);
            }
            W(k, Wbs.GAllee, 0.3f, 2.3f);
            k.Cylinder(new Vector3(-13f, 0.3f, 44f), 7f, 0.65f, 28, Stone, LM.Solid, 1f, Stone, LM.Paving);
            k.Cylinder(new Vector3(-13f, 0.3f, 44f), 6.2f, 0.6f, 28, Stone, LM.Solid, 1f, Water, LM.Water);
            k.Cylinder(new Vector3(-13f, 0.9f, 44f), 1.1f, 1.4f, 12, Stone, LM.Solid, 1f, Water, LM.Water);
            // the parterre north of the tower: four lawn panels, a cross of paths, a row of trees along it
            W(k, Wbs.GSquare, 0.3f, 1f);
            k.Prism(LandmarkKit.Rect(39f, 72f, 66f, 22f), 0.3f, 0.36f, Stone, LM.Solid, 1f, Pave, LM.Paving);
            foreach (float px in new[] { 22f, 56f }) foreach (float pz in new[] { 66.5f, 77.5f }) Lawn(k, px, pz, 28f, 8f, 1.5f);
            W(k, Wbs.GTrees, 0.3f, 9f);
            for (float x = 10f; x <= 68f; x += 9.5f) Planted(k, x, 61.5f, 6.5f, 2);
            // the square east of the tower: a long reflecting pool between two rows of trees
            W(k, Wbs.GSquare, 0.3f, 1f);
            k.Prism(LandmarkKit.Rect(97f, 42f, 46f, 80f), 0.3f, 0.36f, Stone, LM.Solid, 1f, Pave, LM.Paving);
            k.Prism(LandmarkKit.Rect(97f, 42f, 12f, 44f), 0.36f, 0.75f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Rect(97f, 42f, 10.4f, 42.4f), 0.75f, 0.8f, Stone, LM.Solid, 1f, Water, LM.Water);
            foreach (float px in new[] { 83.5f, 110.5f }) Lawn(k, px, 42f, 9f, 64f, 1.5f);
            W(k, Wbs.GTrees, 0.3f, 9f);
            for (float z = 14f; z <= 72f; z += 9.5f) { Planted(k, 83.5f, z, 8f, 3); Planted(k, 110.5f, z, 8f, 4); }
            for (float z = 22f; z <= 64f; z += 14f) foreach (float px in new[] { 89.5f, 104.5f }) Bench(k, px, z, 90f);
            W(k, Wbs.GSquare, 0.3f, 6.5f);
            for (int i = 0; i < 9; i++) k.Box(new Vector3(-6f + i * 10f, 3.2f, 2f), new Vector3(0.35f, 6f, 0.35f), 0, Steel, LM.Steel, 1f, Warm, LM.Light);
            k.Part = 0; k.NoWin();
            IconicShape.P = shape;
        }
        /// <summary>A podium block on the rectangle (x0, z0)–(x1, z1): glass walls, a golden fascia, a flat paved roof terrace with a glass parapet.</summary>
        static void Podium(LandmarkKit k, float x0, float z0, float x1, float z1, float h)
        {
            var r = LandmarkKit.Rect((x0 + x1) * 0.5f, (z0 + z1) * 0.5f, x1 - x0, z1 - z0);
            k.Prism(r, 0.3f, h - 1.6f, WarmGlass, LM.Glass, 4.3f, Fascia, -1);
            k.Prism(LandmarkKit.Rect((x0 + x1) * 0.5f, (z0 + z1) * 0.5f, x1 - x0 + 0.8f, z1 - z0 + 0.8f), h - 1.6f, h, Gold, LM.Solid, 1.6f, Stone, LM.Paving);
            float cx = (x0 + x1) * 0.5f, cz = (z0 + z1) * 0.5f, w = x1 - x0, d = z1 - z0;
            foreach (var (c, sz) in new[] { (new Vector3(cx, h + 0.55f, z0 + 0.3f), new Vector3(w, 1.1f, 0.12f)), (new Vector3(cx, h + 0.55f, z1 - 0.3f), new Vector3(w, 1.1f, 0.12f)),
                                           (new Vector3(x0 + 0.3f, h + 0.55f, cz), new Vector3(0.12f, 1.1f, d)), (new Vector3(x1 - 0.3f, h + 0.55f, cz), new Vector3(0.12f, 1.1f, d)) })
                k.Box(c, sz, 0f, GlassBlue, LM.Glass, 1.1f, Fascia, LM.Solid);
        }
        /// <summary>A pool on a roof at height y: timber deck, stone coping, the water, sun loungers with parasols along the long sides, planters at the ends.
        /// yaw 0: the pool runs along x; 90: along z.</summary>
        static void RoofPool(LandmarkKit k, float cx, float cz, float lx, float lz, float y, float yaw)
        {
            k.Prism(LandmarkKit.Rect(cx, cz, lx + 16f, lz + 14f), y, y + 0.14f, Timber, LM.Solid, 1f, Timber, LM.Paving);
            k.Prism(LandmarkKit.Rect(cx, cz, lx, lz), y + 0.14f, y + 0.42f, PoolTile, LM.Solid, 1f, PoolWater, LM.Water);
            foreach (var (c, sz) in new[] { (new Vector3(cx, y + 0.3f, cz - lz * 0.5f - 0.5f), new Vector3(lx + 2f, 0.32f, 1f)), (new Vector3(cx, y + 0.3f, cz + lz * 0.5f + 0.5f), new Vector3(lx + 2f, 0.32f, 1f)),
                                           (new Vector3(cx - lx * 0.5f - 0.5f, y + 0.3f, cz), new Vector3(1f, 0.32f, lz)), (new Vector3(cx + lx * 0.5f + 0.5f, y + 0.3f, cz), new Vector3(1f, 0.32f, lz)) })
                k.Box(c, sz, 0f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            bool alongX = yaw < 45f; float len = alongX ? lx : lz, side = (alongX ? lz : lx) * 0.5f + 3.6f;
            for (float t = -len * 0.5f + 3f; t <= len * 0.5f - 3f; t += 4.2f)
                foreach (float sgn in new[] { -1f, 1f })
                {
                    var p = alongX ? new Vector3(cx + t, y, cz + sgn * side) : new Vector3(cx + sgn * side, y, cz + t);
                    var sz = alongX ? new Vector3(0.75f, 0.32f, 1.9f) : new Vector3(1.9f, 0.32f, 0.75f);
                    k.Box(p + Vector3.up * 0.3f, sz, 0f, White, LM.Solid, 1f, White, LM.Solid);
                    k.Box(p + Vector3.up * 0.3f + (alongX ? new Vector3(0.95f, 0f, 0f) : new Vector3(0f, 0f, 0.95f)), sz, 0f, White, LM.Solid, 1f, White, LM.Solid);
                    var u = p + (alongX ? new Vector3(0.47f, 0f, sgn * 1.6f) : new Vector3(sgn * 1.6f, 0f, 0.47f));
                    k.Beam(u + Vector3.up * 0.14f, u + Vector3.up * 2.4f, 0.08f, 0.08f, MetalG, LM.Metal);
                    k.Cylinder(u + Vector3.up * 2.3f, 1.5f, 0.1f, 10, Fascia, LM.Solid, 1f, Fascia, LM.Solid, 0.35f);
                }
            foreach (float e in new[] { -1f, 1f })
                for (int i = -1; i <= 1; i++)
                {
                    var c = alongX ? new Vector3(cx + e * (lx * 0.5f + 5.5f), y, cz + i * lz * 0.32f) : new Vector3(cx + i * lx * 0.32f, y, cz + e * (lz * 0.5f + 5.5f));
                    k.Box(c + Vector3.up * 0.5f, new Vector3(2.2f, 0.8f, 2.2f), 0f, Stone, LM.Solid, 1f, Grass, LM.Plant);
                    k.Tree(c + Vector3.up * 0.9f, 4.2f, Leaf2, c.x * 0.13f + c.z * 0.07f);
                }
        }
        /// <summary>A planted roof terrace: lawn beds in timber edging, paths between them, small trees in rows.</summary>
        static void RoofGarden(LandmarkKit k, float cx, float cz, float lx, float lz, float y)
        {
            for (int i = -1; i <= 1; i += 2)
                for (int j = -1; j <= 1; j += 2)
                {
                    float bx = cx + i * lx * 0.24f, bz = cz + j * lz * 0.24f;
                    k.Prism(LandmarkKit.RoundRect(bx, bz, lx * 0.38f, lz * 0.38f, 1.5f, 2), y, y + 0.55f, Timber, LM.Solid, 1f, Grass, LM.Plant);
                    for (float t = -lz * 0.15f; t <= lz * 0.15f + 0.01f; t += lz * 0.15f) k.Tree(new Vector3(bx, y + 0.55f, bz + t), 4.6f, Leaf, bx * 0.11f + t);
                }
            for (int i = -1; i <= 1; i += 2) Bench(k, cx, cz + i * 3f, 0f, y);
        }
        /// <summary>A tree in a square grate (the clipped trees of the alleys): same height and shape along a row.</summary>
        static void Planted(LandmarkKit k, float x, float z, float h, int row)
        {
            k.Box(new Vector3(x, 0.34f, z), new Vector3(1.8f, 0.08f, 1.8f), 0f, Steel, LM.Solid, 1f, Steel, LM.Paving);
            k.Tree(new Vector3(x, 0.38f, z), h, (row & 1) == 0 ? Leaf : Leaf2, row * 1.7f);
        }
        static void Bench(LandmarkKit k, float x, float z, float yaw, float y = 0.3f)
        {
            k.Box(new Vector3(x, y + 0.42f, z), new Vector3(2.2f, 0.12f, 0.6f), yaw, Timber, LM.Solid, 1f, Timber, LM.Solid);
            k.Box(new Vector3(x, y + 0.2f, z), new Vector3(1.8f, 0.4f, 0.4f), yaw, Steel, LM.Solid, 1f, Steel, LM.Solid);
        }
        /// <summary>The promenade around the plot: a 12 m paved band along the edge with two rows of clipped trees in grates, lamps between
        /// the outer trees, benches, and a clipped hedge on the inner side with openings at the entrances. Trees and hedges keep off the buildings.</summary>
        static void Promenade(LandmarkKit k, float w, float d, List<Rect> keepOff)
        {
            float hw = w * 0.5f, hd = d * 0.5f, i0 = 4f, i1 = 16f;
            bool Free(float x, float z, float m) { foreach (var r in keepOff) if (x > r.xMin - m && x < r.xMax + m && z > r.yMin - m && z < r.yMax + m) return false; return true; }
            // the paving band (four strips) with a lighter centre line — laid first, then trees, lamps and benches, the hedge last (Wbs.G*)
            W(k, Wbs.GProm, 0.3f, 0.4f);
            k.Prism(LandmarkKit.Rect(0f, -hd + (i0 + i1) * 0.5f, w - 2f * i0, i1 - i0), 0.3f, 0.36f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Rect(0f, hd - (i0 + i1) * 0.5f, w - 2f * i0, i1 - i0), 0.3f, 0.36f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Rect(-hw + (i0 + i1) * 0.5f, 0f, i1 - i0, d - 2f * i1), 0.3f, 0.36f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Rect(hw - (i0 + i1) * 0.5f, 0f, i1 - i0, d - 2f * i1), 0.3f, 0.36f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            // walk the ring at a given inset: f(x, z, along-direction)
            void Ring(float inset, float step, System.Action<float, float, Vector2> f)
            {
                float ax = hw - inset, az = hd - inset;
                for (float x = -ax; x <= ax + 0.01f; x += step) { f(x, -az, Vector2.right); f(x, az, Vector2.right); }
                for (float z = -az + step; z <= az - step + 0.01f; z += step) { f(-ax, z, Vector2.up); f(ax, z, Vector2.up); }
            }
            int n = 0;
            W(k, Wbs.GTrees, 0.3f, 9f);
            Ring(6.5f, 9f, (x, z, dir) => { if (Free(x, z, 2.5f)) Planted(k, x, z, 8f, 0); });
            Ring(13.5f, 9f, (x, z, dir) => { if (Free(x, z, 2.5f)) Planted(k, x, z, 8f, 1); });
            W(k, Wbs.GSquare, 0.3f, 6.5f);
            Ring(6.5f, 9f, (x, z, dir) =>
            {
                float lx = x + dir.x * 4.5f, lz = z + dir.y * 4.5f; if (!Free(lx, lz, 1.5f) || Mathf.Abs(lx) > hw - 6f || Mathf.Abs(lz) > hd - 6f) return;
                k.Box(new Vector3(lx, 3.3f, lz), new Vector3(0.22f, 6f, 0.22f), 0f, Steel, LM.Steel, 1f, Warm, LM.Light);
                if ((n++ % 3) == 0) { float bx = x + dir.x * 4.5f + dir.y * 3.5f, bz = z + dir.y * 4.5f + dir.x * 3.5f; if (Free(bx, bz, 1.5f)) Bench(k, bx, bz, dir.x != 0f ? 0f : 90f); }
            });
            // clipped hedge on the inner edge, open at the middle of each side (entrances)
            void Hedge(Vector2 a, Vector2 b)
            {
                var dl = b - a; float L = dl.magnitude; var u = dl / L;
                for (float t = 0f; t < L - 0.1f; t += 6f)
                {
                    var p = a + u * (t + 2.5f); if (t + 5f > L) break;
                    if (!Free(p.x, p.y, 3f)) continue;
                    if (Mathf.Abs(u.x) > 0.5f ? Mathf.Abs(p.x) < 14f : Mathf.Abs(p.y) < 14f) continue;
                    k.Box(new Vector3(p.x, 0.75f, p.y), Mathf.Abs(u.x) > 0.5f ? new Vector3(5f, 0.9f, 1.2f) : new Vector3(1.2f, 0.9f, 5f), 0f, GrassDark, LM.Plant, 1f, Grass, LM.Plant);
                }
            }
            float hx = hw - i1 - 1f, hz = hd - i1 - 1f;
            W(k, Wbs.GTrees, 0.3f, 1.3f);
            Hedge(new Vector2(-hx, hz), new Vector2(hx, hz)); Hedge(new Vector2(-hx, -hz), new Vector2(hx, -hz));
            Hedge(new Vector2(-hx, -hz), new Vector2(-hx, hz)); Hedge(new Vector2(hx, -hz), new Vector2(hx, hz));
        }
        /// <summary>A golden floor plate: a ring between the glass line and a footprint 1.4 m larger, turned a little (the "sliced" facade).</summary>
        static void Plate(LandmarkKit k, List<Vector2> glass, float y, int fl, bool crown)
        {
            float th = 1.4f * Mathf.Sin(y / 34f) + ((fl & 1) == 0 ? 0.35f : -0.35f);
            Vector2 c = Vector2.zero; foreach (var p in glass) c += p; c /= glass.Count;
            var outer = new List<Vector2>(glass.Count);
            float a = th * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a);
            foreach (var p in glass)
            {
                var d = p - c; float L = d.magnitude; var g = L > 0.01f ? d * ((L + 1.4f) / L) : d;
                outer.Add(c + new Vector2(g.x * ca - g.y * sa, g.x * sa + g.y * ca));
            }
            float y0 = y - 0.42f, y1 = y + 0.12f;
            var col = crown ? GoldLight : Gold; int mat = crown ? LM.Light : LM.Solid;
            k.Prism(outer, y0, y1, col, mat, 0.6f, col, -1);
            for (int i = 0; i < glass.Count; i++)
            {
                int j = (i + 1) % glass.Count;
                Vector3 gi = new Vector3(glass[i].x, y1, glass[i].y), gj = new Vector3(glass[j].x, y1, glass[j].y), oi = new Vector3(outer[i].x, y1, outer[i].y), oj = new Vector3(outer[j].x, y1, outer[j].y);
                k.Quad(gi, gj, oj, oi, Vector3.up, Gold, LM.Solid, 0.6f, glass[i], glass[j], outer[j], outer[i]);
                gi.y = gj.y = oi.y = oj.y = y0;
                k.Quad(gi, gj, oj, oi, Vector3.down, Gold, LM.Solid, 0.6f, glass[i], glass[j], outer[j], outer[i]);
            }
        }
        /// <summary>A low block on the rectangle (x0, z0)–(x1, z1) whose roof follows H(x, z): glass walls under a golden fascia, a planted roof with paths.</summary>
        static void Wedge(LandmarkKit k, float x0, float z0, float x1, float z1, System.Func<float, float, float> Hf, int nx, int nz)
        {
            var corners = new[] { new Vector2(x0, z0), new Vector2(x1, z0), new Vector2(x1, z1), new Vector2(x0, z1) };
            var ce = new Vector2((x0 + x1) * 0.5f, (z0 + z1) * 0.5f);
            for (int e = 0; e < 4; e++)
            {
                var a = corners[e]; var b = corners[(e + 1) % 4]; int n = e % 2 == 0 ? nx : nz;
                var mid = (a + b) * 0.5f; var o = new Vector3(mid.x - ce.x, 0f, mid.y - ce.y);
                for (int i = 0; i < n; i++)
                {
                    var p = Vector2.Lerp(a, b, i / (float)n); var q = Vector2.Lerp(a, b, (i + 1f) / n);
                    float hp = Hf(p.x, p.y), hq = Hf(q.x, q.y), u0 = (p - a).magnitude, u1 = (q - a).magnitude;
                    k.Quad(new Vector3(p.x, 0.3f, p.y), new Vector3(q.x, 0.3f, q.y), new Vector3(q.x, hq - 1.4f, q.y), new Vector3(p.x, hp - 1.4f, p.y), o, WarmGlass, LM.Glass, 4.3f,
                           new Vector2(u0, 0.3f), new Vector2(u1, 0.3f), new Vector2(u1, hq - 1.4f), new Vector2(u0, hp - 1.4f));
                    k.Quad(new Vector3(p.x, hp - 1.4f, p.y), new Vector3(q.x, hq - 1.4f, q.y), new Vector3(q.x, hq, q.y), new Vector3(p.x, hp, p.y), o, Gold, LM.Solid, 1.4f,
                           new Vector2(u0, hp - 1.4f), new Vector2(u1, hq - 1.4f), new Vector2(u1, hq), new Vector2(u0, hp));
                }
            }
            for (int i = 0; i < nx; i++)
                for (int j = 0; j < nz; j++)
                {
                    float xa = Mathf.Lerp(x0, x1, i / (float)nx), xb = Mathf.Lerp(x0, x1, (i + 1f) / nx), za = Mathf.Lerp(z0, z1, j / (float)nz), zb = Mathf.Lerp(z0, z1, (j + 1f) / nz);
                    bool path = (i + j) % 4 == 0;
                    k.Quad(new Vector3(xa, Hf(xa, za), za), new Vector3(xb, Hf(xb, za), za), new Vector3(xb, Hf(xb, zb), zb), new Vector3(xa, Hf(xa, zb), zb), Vector3.up,
                           path ? Pave : Grass, path ? LM.Paving : LM.Plant, 1f, new Vector2(xa, za), new Vector2(xb, za), new Vector2(xb, zb), new Vector2(xa, zb));
                }
        }

        // ------------------------------------------------------------------ airliner (≈ A320): fuselage along +z, nose at +z
        public static void Plane(LandmarkKit k, Vector3 o, float yaw, float scale = 1f)
        {
            var r = Quaternion.Euler(0, yaw, 0);
            Vector3 P(float x, float y, float z) => o + r * (new Vector3(x, y, z) * scale);
            var body = LM.C("#f4f5f6"); var belly = LM.C("#dfe3e8"); var tail = LM.C("#e0261b"); var eng = LM.C("#8a9097"); var win = LM.C("#1d2a36");
            k.Tube(P(0, 4.2f, -16f), P(0, 4.2f, 14f), 2.0f, 2.0f, 10, body, LM.Solid, false);
            k.Tube(P(0, 4.2f, 14f), P(0, 4.0f, 19.5f), 2.0f, 0.25f, 10, body, LM.Solid);            // nose
            k.Tube(P(0, 4.2f, -16f), P(0, 5.0f, -23f), 2.0f, 0.35f, 10, body, LM.Solid);           // tail cone
            k.Tube(P(0, 4.9f, 15.6f), P(0, 4.9f, 17.4f), 1.2f, 0.9f, 8, win, LM.Glass, false);     // cockpit glazing band
            // wings (swept), with engines underneath
            k.Slab(P(1.6f, 3.4f, 3f), P(17f, 4.6f, -5.5f), P(17f, 4.6f, -8f), P(1.6f, 3.4f, -4f), 0.35f, belly, LM.Solid);
            k.Slab(P(-1.6f, 3.4f, -4f), P(-17f, 4.6f, -8f), P(-17f, 4.6f, -5.5f), P(-1.6f, 3.4f, 3f), 0.35f, belly, LM.Solid);
            k.Tube(P(5.8f, 2.4f, 1.8f), P(5.8f, 2.4f, -2.6f), 1.05f, 0.85f, 10, eng, LM.Metal);
            k.Tube(P(-5.8f, 2.4f, 1.8f), P(-5.8f, 2.4f, -2.6f), 1.05f, 0.85f, 10, eng, LM.Metal);
            // tail: fin + stabilisers
            k.Slab(P(0, 5.6f, -15f), P(0, 12.2f, -20.5f), P(0, 12.2f, -23f), P(0, 5.6f, -21.5f), 0.3f, tail, LM.Solid);
            k.Slab(P(0.5f, 5.2f, -18.5f), P(6.2f, 5.6f, -21.5f), P(6.2f, 5.6f, -22.8f), P(0.5f, 5.2f, -22f), 0.25f, body, LM.Solid);
            k.Slab(P(-0.5f, 5.2f, -22f), P(-6.2f, 5.6f, -22.8f), P(-6.2f, 5.6f, -21.5f), P(-0.5f, 5.2f, -18.5f), 0.25f, body, LM.Solid);
            // gear
            k.Box(P(0, 1.1f, 13f), new Vector3(0.5f, 2.2f, 0.5f) * scale, yaw, eng, LM.Steel, 1f, eng, LM.Steel);
            k.Box(P(2.6f, 1.1f, -1f), new Vector3(0.8f, 2.2f, 1.2f) * scale, yaw, eng, LM.Steel, 1f, eng, LM.Steel);
            k.Box(P(-2.6f, 1.1f, -1f), new Vector3(0.8f, 2.2f, 1.2f) * scale, yaw, eng, LM.Steel, 1f, eng, LM.Steel);
        }
        public static Mesh PlaneMesh() { var k = new LandmarkKit(); Plane(k, Vector3.zero, 0f); return k.ToMesh("Airliner"); }

        // ------------------------------------------------------------------ Airport (concept): two parallel runways and, between them, a terminal in the shape
        // of an airliner — the glazed nose is the landside hall facing the city, the swept wings, the fuselage and the tailplane are the piers
        // with the gates; cargo, maintenance, the tower and the fuel farm north of the apron; the landside (gate roundabout, boulevard, forecourt,
        // car parks, hotel, LRT station) south of it. Local frame: x across (+ = east-south-east), z along the runways (− = toward the city).
        public const float RwyLX = -640f, RwyLZ0 = -1650f, RwyLZ1 = 1750f, RwyRX = 640f, RwyRZ0 = -900f, RwyRZ1 = 1750f;
        const float TermZ = -300f;           // terminal origin on the plot (its nose tip is 560 m south of it)
        static readonly Color32 Tarmac = LM.C("#4a4b4d"), Shoulder = LM.C("#77766f"), ApronC = LM.C("#a3a19a"), Line = LM.C("#f2f2ef"), Yellow = LM.C("#e8b923"),
            GreenL = LM.C("#40e070"), RedL = LM.C("#ff3a2a"), BlueL = LM.C("#3a7bff"), Teal = LM.C("#127a8f"), Turf = LM.C("#8c925e"), Turf2 = LM.C("#848a57");

        /// <summary>An open cross-section (ground → over the top → ground): superelliptic, so the walls stand up near the ground and the roof is full.</summary>
        static List<Vector3> Section(Vector3 c, Vector3 across, float halfW, float h, int m)
        {
            var l = new List<Vector3>(m + 1);
            for (int j = 0; j <= m; j++)
            {
                float th = Mathf.PI * j / m, cs = Mathf.Cos(th), sn = Mathf.Sin(th);
                l.Add(c - across * (Mathf.Sign(cs) * Mathf.Pow(Mathf.Abs(cs), 0.5f) * halfW) + Vector3.up * (Mathf.Pow(Mathf.Max(sn, 0f), 0.62f) * h));
            }
            return l;
        }
        /// <summary>A vaulted shell lofted through sections; mat(ring, f) picks glass or metal for each strip (f = 0 on the ridge … 1 at the foot of the wall).</summary>
        static void Shell(LandmarkKit k, List<List<Vector3>> rings, System.Func<int, float, int> mat, Color32 roof, Color32 glass, bool capA, bool capB)
        {
            int m = rings[0].Count - 1; float s = 0f;
            for (int i = 0; i + 1 < rings.Count; i++)
            {
                var A = rings[i]; var B = rings[i + 1];
                Vector3 cen = (A[0] + A[m] + B[0] + B[m]) * 0.25f; float ds = Vector3.Distance((A[0] + A[m]) * 0.5f, (B[0] + B[m]) * 0.5f);
                Vector3 acr = (A[m] - A[0] + B[m] - B[0]) * 0.5f; float hw = Mathf.Max(acr.magnitude * 0.5f, 0.01f); acr.Normalize();
                float v = 0f;
                for (int j = 0; j < m; j++)
                {
                    Vector3 a = A[j], b = A[j + 1], c = B[j + 1], d = B[j]; float L = (b - a).magnitude;
                    int mm = mat(i, Mathf.Abs(Vector3.Dot((a + b + c + d) * 0.25f - cen, acr)) / hw); bool g = mm == LM.Glass;
                    k.Quad(a, b, c, d, (a + b + c + d) * 0.25f - cen, g ? glass : roof, mm, g ? 4.5f : 3f,
                           new Vector2(s, v), new Vector2(s, v + L), new Vector2(s + ds, v + L), new Vector2(s + ds, v));
                    v += L;
                }
                s += ds;
            }
            void Cap(List<Vector3> R, Vector3 outward)
            {
                var c0 = (R[0] + R[m]) * 0.5f;
                for (int j = 0; j < m; j++) k.Tri(c0, R[j], R[j + 1], outward, roof, LM.Metal, 3f, new Vector2(c0.x, c0.z), new Vector2(R[j].x, R[j].z), new Vector2(R[j + 1].x, R[j + 1].z));
            }
            Vector3 Mid(List<Vector3> R) => (R[0] + R[m]) * 0.5f;
            if (capA) Cap(rings[0], Mid(rings[0]) - Mid(rings[1]));
            if (capB) Cap(rings[rings.Count - 1], Mid(rings[rings.Count - 1]) - Mid(rings[rings.Count - 2]));
        }
        /// <summary>A contact stand: guide line, a jet bridge from the facade point e (outward normal n) to the front door, and the aircraft nose-in.</summary>
        static void Stand(LandmarkKit k, Vector3 e, Vector3 n, float scale, bool plane)
        {
            n.y = 0; n.Normalize(); e.y = 0f;
            float yaw = Mathf.Atan2(-n.x, -n.z) * Mathf.Rad2Deg; var r = Quaternion.Euler(0, yaw, 0);
            var o = e + n * (19.5f * scale + 13f); o.y = 0.45f;
            k.Beam(e + n * 3f + Vector3.up * 0.47f, e + n * (46f * scale + 22f) + Vector3.up * 0.47f, 0.35f, 0.04f, Yellow, LM.Light);
            k.Beam(o + r * new Vector3(-9f, 0.02f, 0f), o + r * new Vector3(9f, 0.02f, 0f), 0.3f, 0.04f, Yellow, LM.Light);       // stop bar
            var door = o + r * (new Vector3(-2.3f, 4.0f, 14.5f) * scale);
            var root = e + n * 1.5f + Vector3.up * 5.2f;
            k.Beam(root, door, 3.2f, 3.0f, MetalG, LM.Metal);
            var leg = Vector3.Lerp(root, door, 0.72f);
            k.Beam(new Vector3(leg.x, 0.45f, leg.z), leg - Vector3.up * 1.5f, 0.7f, 0.7f, MetalD, LM.Steel);
            k.Box(new Vector3(leg.x, 0.9f, leg.z), new Vector3(3.4f, 0.9f, 1.4f), yaw, MetalD, LM.Steel, 1f, MetalD, LM.Steel);
            if (plane) Plane(k, o, yaw, scale);
            else k.Box(o + r * new Vector3(6f, 1.2f, -6f), new Vector3(2.4f, 2.0f, 5.5f), yaw, Yellow, LM.Solid, 2f, Yellow, LM.Roof);  // tug waiting
        }
        static void Runway(LandmarkKit k, float x, float z0, float z1, bool approachSouth)
        {
            float L = z1 - z0, zc = (z0 + z1) * 0.5f;
            k.Prism(LandmarkKit.Rect(x, zc, 76f, L + 12f), 0.25f, 0.40f, Shoulder, LM.Solid, 1f, Shoulder, LM.Paving);
            k.Prism(LandmarkKit.Rect(x, zc, 60f, L), 0.25f, 0.45f, Tarmac, LM.Solid, 1f, Tarmac, LM.Paving);
            void Mark(float cx, float cz, float w, float d, Color32 c) => k.Box(new Vector3(cx, 0.47f, cz), new Vector3(w, 0.04f, d), 0, c, LM.Solid, 1f, c, LM.Light);
            for (float z = z0 + 330f; z < z1 - 330f; z += 60f) Mark(x, z, 0.9f, 30f, Line);
            Mark(x - 29f, zc, 0.7f, L - 20f, Line); Mark(x + 29f, zc, 0.7f, L - 20f, Line);
            foreach (float sg in new[] { -1f, 1f })
            {
                float zt = sg < 0 ? z0 + 26f : z1 - 26f, inw = -sg;           // threshold, and the direction into the runway
                for (int i = 0; i < 8; i++) { float xo = -25f + i * 6.8f + (i >= 4 ? 3.2f : 0f); Mark(x + xo, zt, 1.8f, 30f, Line); }
                Mark(x, zt + inw * 24f, 56f, 1.6f, Line);
                Mark(x - 10.5f, zt + inw * 400f, 9f, 50f, Line); Mark(x + 10.5f, zt + inw * 400f, 9f, 50f, Line);      // aiming point
                for (int i = 0; i < 3; i++) { float zz = zt + inw * (190f + i * 150f); if (i == 1) continue; Mark(x - 12f, zz, 3f, 22f, Line); Mark(x + 12f, zz, 3f, 22f, Line); Mark(x - 17f, zz, 3f, 22f, Line); Mark(x + 17f, zz, 3f, 22f, Line); }
                // threshold (green) and runway end (red) lights
                for (int i = 0; i < 12; i++) { float xo = -30f + i * 5.45f; float ze = sg < 0 ? z0 : z1; k.Box(new Vector3(x + xo, 0.7f, ze + inw * 1.5f), new Vector3(0.6f, 0.5f, 0.6f), 0, GreenL, LM.Light, 1f, GreenL, LM.Light); k.Box(new Vector3(x + xo, 0.7f, ze - inw * 1.5f), new Vector3(0.6f, 0.5f, 0.6f), 0, RedL, LM.Light, 1f, RedL, LM.Light); }
            }
            for (float z = z0; z <= z1 + 0.1f; z += 60f) { k.Box(new Vector3(x - 31f, 0.7f, z), new Vector3(0.5f, 0.5f, 0.5f), 0, Warm, LM.Light, 1f, Warm, LM.Light); k.Box(new Vector3(x + 31f, 0.7f, z), new Vector3(0.5f, 0.5f, 0.5f), 0, Warm, LM.Light, 1f, Warm, LM.Light); }
            // approach lighting from the south (toward the city): centre line bars and two cross bars
            if (approachSouth)
                for (int i = 1; i <= 8; i++)
                {
                    float z = z0 - i * 30f; k.Box(new Vector3(x, 1.4f, z), new Vector3(4.2f, 0.6f, 0.6f), 0, Warm, LM.Light, 1f, Warm, LM.Light);
                    k.Beam(new Vector3(x, 0.25f, z), new Vector3(x, 1.1f, z), 0.3f, 0.3f, Steel, LM.Steel);
                    if (i == 5) k.Box(new Vector3(x, 1.4f, z), new Vector3(30f, 0.5f, 0.6f), 0, Warm, LM.Light, 1f, Warm, LM.Light);
                }
        }
        /// <summary>A taxiway strip between two points: tarmac, yellow centre line, blue edge lights.</summary>
        static void Taxi(LandmarkKit k, Vector2 a, Vector2 b, float w = 23f)
        {
            var d = b - a; float L = d.magnitude; if (L < 1f) return; var m = (a + b) * 0.5f; float yaw = Mathf.Atan2(d.x, d.y) * Mathf.Rad2Deg; var dn = d / L; var side = new Vector2(dn.y, -dn.x);
            k.Prism(LandmarkKit.Rect(m.x, m.y, w + 8f, L, yaw), 0.25f, 0.40f, Shoulder, LM.Solid, 1f, Shoulder, LM.Paving);
            k.Prism(LandmarkKit.Rect(m.x, m.y, w, L, yaw), 0.25f, 0.43f, Tarmac, LM.Solid, 1f, Tarmac, LM.Paving);
            k.Box(new Vector3(m.x, 0.45f, m.y), new Vector3(0.45f, 0.04f, L - 6f), yaw, Yellow, LM.Solid, 1f, Yellow, LM.Light);
            for (float s = 0f; s <= L; s += 60f) foreach (float sg in new[] { -1f, 1f })
                { var p = a + dn * s + side * (sg * (w * 0.5f + 1.5f)); k.Box(new Vector3(p.x, 0.65f, p.y), new Vector3(0.45f, 0.45f, 0.45f), 0, BlueL, LM.Light, 1f, BlueL, LM.Light); }
        }
        /// <summary>A road ribbon along a polyline (or a closed loop): asphalt, kerbs implied by the paving around, dashed lane line.</summary>
        static void Road(LandmarkKit k, IList<Vector2> p, float half, bool closed, bool centreLine = true)
        {
            int n = p.Count, segs = closed ? n : n - 1; float s = 0f;
            Vector2 Side(int i)
            {
                Vector2 a = closed ? p[(i - 1 + n) % n] : p[Mathf.Max(i - 1, 0)], b = closed ? p[(i + 1) % n] : p[Mathf.Min(i + 1, n - 1)];
                var d = (b - a).normalized; return new Vector2(d.y, -d.x);
            }
            for (int i = 0; i < segs; i++)
            {
                int j = (i + 1) % n; Vector2 sa = Side(i) * half, sb = Side(j) * half; float L = (p[j] - p[i]).magnitude;
                Vector3 A(Vector2 q) => new Vector3(q.x, 0.47f, q.y);
                k.Quad(A(p[i] - sa), A(p[i] + sa), A(p[j] + sb), A(p[j] - sb), Vector3.up, Asph, LM.Paving, 1f, new Vector2(p[i].x, p[i].y), new Vector2(p[i].x + 1, p[i].y), new Vector2(p[j].x + 1, p[j].y), new Vector2(p[j].x, p[j].y));
                if (centreLine)
                    for (float t = 2f; t < L - 4f; t += 12f)
                    {
                        var d = (p[j] - p[i]) / L; var q = p[i] + d * (t + 2.5f);
                        k.Box(new Vector3(q.x, 0.5f, q.y), new Vector3(0.18f, 0.04f, 5f), Mathf.Atan2(d.x, d.y) * Mathf.Rad2Deg, Line, LM.Solid, 1f, Line, LM.Light);
                    }
                s += L;
            }
        }
        static List<Vector2> Bez(Vector2 a, Vector2 b, Vector2 c, Vector2 d, int n)
        {
            var l = new List<Vector2>(); for (int i = 0; i <= n; i++) { float t = i / (float)n, u = 1 - t; l.Add(u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d); } return l;
        }
        /// <summary>Surface car park: bays in double rows with aisles, most of them taken.</summary>
        static void CarPark(LandmarkKit k, float x0, float x1, float z0, float z1, float seed)
        {
            k.Prism(LandmarkKit.Rect((x0 + x1) * 0.5f, (z0 + z1) * 0.5f, x1 - x0, z1 - z0), 0.25f, 0.44f, PaveDark, LM.Solid, 1f, LM.C("#6b6b69"), LM.Paving);
            for (float z = z0 + 4f; z + 13f < z1; z += 21f)
            {
                Cars(k, x0 + 3f, z + 2.6f, Mathf.FloorToInt((x1 - x0 - 6f) / 2.7f), 2, seed + z);
                k.Box(new Vector3((x0 + x1) * 0.5f, 0.46f, z + 5.85f), new Vector3(x1 - x0 - 6f, 0.04f, 0.15f), 0, Line, LM.Solid, 1f, Line, LM.Light);
            }
        }

        static void Airport(LandmarkKit k)
        {
            float W = 1600f, D = 3800f;
            // ---- airfield: mown grass over the whole plot, in long stripes along the runways
            k.Prism(LandmarkKit.RoundRect(0, 0, W, D, 60f, 4), -2f, 0.22f, LM.C("#6f7550"), LM.Plant, 3f, Turf, LM.Plant);
            for (int i = 0; i < 20; i++) { float x = -W * 0.5f + 40f + i * 80f; k.Prism(LandmarkKit.Rect(x, 0, 40f, D - 140f), 0.22f, 0.24f, Turf2, LM.Plant, 1f, Turf2, LM.Plant); }

            // ---- runways (west 3.4 km, east 2.65 km with a staggered threshold), parallel taxiways, links and rapid exits
            Runway(k, RwyLX, RwyLZ0, RwyLZ1, true); Runway(k, RwyRX, RwyRZ0, RwyRZ1, false);
            float TA = -460f, TB = 460f;
            Taxi(k, new Vector2(TA, RwyLZ0 + 10f), new Vector2(TA, RwyLZ1 - 10f)); Taxi(k, new Vector2(TB, RwyRZ0 + 10f), new Vector2(TB, RwyRZ1 - 10f));
            foreach (float z in new[] { RwyLZ0 + 12f, -380f, 640f, RwyLZ1 - 12f }) Taxi(k, new Vector2(RwyLX, z), new Vector2(TA, z));
            foreach (float z in new[] { RwyRZ0 + 12f, 260f, RwyRZ1 - 12f }) Taxi(k, new Vector2(RwyRX, z), new Vector2(TB, z));
            foreach (float z in new[] { -900f, 260f }) Taxi(k, new Vector2(RwyLX, z), new Vector2(TA, z + 312f));          // rapid exits (landing north)
            foreach (float z in new[] { 1150f, 60f }) Taxi(k, new Vector2(RwyLX, z), new Vector2(TA, z - 312f));           // (landing south)
            foreach (float z in new[] { -350f, 760f }) Taxi(k, new Vector2(RwyRX, z), new Vector2(TB, z + 312f));
            Taxi(k, new Vector2(RwyRX, 1300f), new Vector2(TB, 1300f - 312f));

            // ---- aprons: the main apron round the terminal, a service apron in front of cargo and maintenance
            k.Prism(LandmarkKit.Rect(0, -80f, 900f, 1360f), 0.25f, 0.44f, ApronC, LM.Solid, 1f, ApronC, LM.Paving);
            k.Prism(LandmarkKit.Rect(0, 720f, 900f, 240f), 0.25f, 0.44f, ApronC, LM.Solid, 1f, ApronC, LM.Paving);
            foreach (float x in new[] { -405f, 405f }) k.Box(new Vector3(x, 0.47f, 40f), new Vector3(0.45f, 0.04f, 1560f), 0, Yellow, LM.Solid, 1f, Yellow, LM.Light);     // apron taxilanes
            k.Box(new Vector3(0, 0.47f, 560f), new Vector3(800f, 0.04f, 0.45f), 0, Yellow, LM.Solid, 1f, Yellow, LM.Light);
            // flood-light masts round the apron
            for (int i = 0; i < 7; i++) foreach (float x in new[] { -440f, 440f })
            {
                float z = -720f + i * 210f; k.Beam(new Vector3(x, 0.4f, z), new Vector3(x, 28f, z), 0.8f, 0.8f, MetalG, LM.Steel);
                k.Box(new Vector3(x, 28.6f, z), new Vector3(4.5f, 1.2f, 1.6f), 0, Warm, LM.Light, 1f, Steel, LM.Steel);
            }

            // ---- the terminal: an airliner 985 m long, 776 m span (local frame of the terminal: origin at TermZ, nose at -z)
            var T = new Vector3(0, 0, TermZ);
            // fuselage: (z, half width, height)
            float[,] fs = { { -560, 3, 4 }, { -553, 17, 14 }, { -540, 29, 22 }, { -518, 40, 30 }, { -488, 48, 36 }, { -450, 53, 40 }, { -400, 56, 42 }, { -150, 56, 42 },
                            { 120, 56, 42 }, { 200, 54, 40 }, { 270, 48, 36 }, { 330, 38, 30 }, { 380, 25, 22 }, { 412, 11, 15 }, { 425, 3, 9 } };
            var rings = new List<List<Vector3>>(); var fz = new List<float>();
            for (int i = 0; i < fs.GetLength(0); i++) { rings.Add(Section(T + new Vector3(0, 0, fs[i, 0]), Vector3.right, fs[i, 1], fs[i, 2], 18)); fz.Add(fs[i, 0]); }
            Shell(k, rings, (i, t) =>
            {
                if (fz[i] < -470f) return LM.Glass;                                                   // the glazed nose: landside hall
                if (t > 0.965f) return LM.Glass;                                                      // facades to the apron
                if (t < 0.035f) return LM.Glass;                                                      // ridge roof light
                return LM.Metal;
            }, MetalW, GlassBlue, true, true);
            // cockpit visor on the nose
            k.Quad(T + new Vector3(-22f, 25f, -536f), T + new Vector3(22f, 25f, -536f), T + new Vector3(30f, 31f, -517f), T + new Vector3(-30f, 31f, -517f), new Vector3(0, 1f, -1f), GlassDark, LM.Glass, 4f,
                   new Vector2(0, 0), new Vector2(44, 0), new Vector2(60, 8), new Vector2(0, 8));
            // wings: sections across the chord, swept 27°, root chord 200 m, tip 60 m; winglets
            float LE(float x) => -120f + (x - 56f) * 0.51f;
            float TE(float x) => 80f + (x - 56f) * 0.077f;
            float WingH(float x) => Mathf.Lerp(30f, 13f, Mathf.InverseLerp(56f, 388f, x));
            foreach (float sg in new[] { -1f, 1f })
            {
                var wr = new List<List<Vector3>>();
                foreach (float x in new[] { 36f, 56f, 110f, 170f, 230f, 290f, 350f, 388f })
                {
                    float le = LE(Mathf.Max(x, 56f)), te = TE(Mathf.Max(x, 56f));
                    wr.Add(Section(T + new Vector3(sg * x, 0, (le + te) * 0.5f), Vector3.forward * sg, (te - le) * 0.5f, WingH(x), 14));
                }
                Shell(k, wr, (i, t) => t > 0.96f || t < 0.04f ? LM.Glass : LM.Metal, MetalW, GlassBlue, false, true);
                float tx = sg * 388f, tle = LE(388f), tte = TE(388f);
                k.Slab(T + new Vector3(tx, 11f, tle + 22f), T + new Vector3(tx + sg * 6f, 34f, tte - 4f), T + new Vector3(tx + sg * 6f, 34f, tte + 6f), T + new Vector3(tx, 9f, tte), 2.4f, MetalW, LM.Metal);
                k.Box(T + new Vector3(tx + sg * 6f, 34.6f, tte + 2f), new Vector3(1.4f, 1.2f, 1.4f), 0, sg < 0 ? RedL : GreenL, LM.Light, 1f, sg < 0 ? RedL : GreenL, LM.Light);
                // engines: two nacelle pavilions under the leading edge
                foreach (float ex in new[] { 165f, 285f })
                {
                    float z0 = LE(ex) - 46f, z1 = LE(ex) + 12f;
                    k.Tube(T + new Vector3(sg * ex, 11f, z0), T + new Vector3(sg * ex, 11f, z1), 11.5f, 10f, 16, MetalG, LM.Metal);
                    k.Tube(T + new Vector3(sg * ex, 11f, z0 - 0.3f), T + new Vector3(sg * ex, 11f, z0 + 0.2f), 9.6f, 9.6f, 16, GlassDark, LM.Glass);
                    k.Box(T + new Vector3(sg * ex, 14f, z1 + 4f), new Vector3(5f, 10f, 16f), 0, MetalG, LM.Metal, 3f, MetalG, LM.Metal);     // pylon
                }
                // tailplane
                var hr = new List<List<Vector3>>();
                foreach (float x in new[] { 20f, 40f, 90f, 150f })
                {
                    float le = 300f + (x - 20f) * 0.55f, te = 400f + (x - 20f) * 0.09f;
                    hr.Add(Section(T + new Vector3(sg * x, 0, (le + te) * 0.5f), Vector3.forward * sg, (te - le) * 0.5f, Mathf.Lerp(22f, 10f, (x - 20f) / 130f), 10));
                }
                Shell(k, hr, (i, t) => t > 0.96f ? LM.Glass : LM.Metal, MetalW, GlassBlue, false, true);
            }
            // fin: a white sail with a teal leading band and the obstacle light
            k.Slab(T + new Vector3(0, 30f, 236f), T + new Vector3(0, 88f, 368f), T + new Vector3(0, 90f, 402f), T + new Vector3(0, 12f, 422f), 5f, MetalW, LM.Metal);
            k.Slab(T + new Vector3(0, 34f, 244f), T + new Vector3(0, 86f, 362f), T + new Vector3(0, 87.5f, 374f), T + new Vector3(0, 36f, 262f), 5.6f, Teal, LM.Solid);
            k.Box(T + new Vector3(0, 91f, 386f), new Vector3(1.4f, 1.4f, 1.4f), 0, RedL, LM.Light, 1f, RedL, LM.Light);

            // ---- contact stands (32): fuselage sides, wing leading and trailing edges, tailplane
            int sn = 0;
            bool Busy() { sn++; return (sn * 7 % 10) < 8; }
            foreach (float sg in new[] { -1f, 1f })
            {
                var nx = new Vector3(sg, 0, 0);
                foreach (float z in new[] { -420f, -350f, -280f, -210f }) Stand(k, T + new Vector3(sg * 56f, 0, z), nx, z < -400f ? 1.25f : 1f, Busy());
                foreach (float z in new[] { 205f, 262f }) Stand(k, T + new Vector3(sg * 53f, 0, z), nx, 1f, Busy());
                var nLE = new Vector3(sg * 0.453f, 0, -0.891f); var nTE = new Vector3(-sg * 0.077f, 0, 0.997f);
                foreach (float x in new[] { 112f, 222f, 342f }) Stand(k, T + new Vector3(sg * x, 0, LE(x)), nLE, 1f, Busy());
                foreach (float x in new[] { 112f, 168f, 224f, 280f, 336f }) Stand(k, T + new Vector3(sg * x, 0, TE(x)), nTE, 1f, Busy());
                var nHT = new Vector3(-sg * 0.09f, 0, 0.996f);
                foreach (float x in new[] { 72f, 126f }) Stand(k, T + new Vector3(sg * x, 0, 400f + (x - 20f) * 0.09f), nHT, 1f, Busy());
            }
            // remote stands north of the tail and a few service vehicles
            foreach (float x in new[] { -360f, -270f, -180f, 180f, 270f, 360f }) { Plane(k, new Vector3(x, 0.45f, 430f), 180f, 1f); k.Box(new Vector3(x + 14f, 1.6f, 400f), new Vector3(2.6f, 2.9f, 12f), 0, White, LM.Solid, 2f, White, LM.Roof); }
            for (int i = 0; i < 16; i++) { float x = (i % 2 == 0 ? -1f : 1f) * (392f + (i % 3) * 7f), z = -640f + i * 52f; k.Box(new Vector3(x, 1.2f, z), new Vector3(2.6f, 2.2f, 6f), 0f, Yellow, LM.Solid, 2f, Yellow, LM.Roof); }

            // ---- north side: cargo terminal with two freighters, two maintenance hangars, the control tower, fuel farm, fire station
            k.Prism(LandmarkKit.Rect(-285f, 930f, 270f, 170f), 0.3f, 17f, MetalG, LM.Metal, 4f, Roof, LM.Roof);
            for (int i = 0; i < 9; i++) k.Box(new Vector3(-400f + i * 29f, 4.5f, 844.6f), new Vector3(12f, 8f, 0.8f), 0, MetalD, LM.Metal, 2f, MetalD, LM.Metal);   // dock doors
            Plane(k, new Vector3(-350f, 0.45f, 790f), 0f, 1.5f); Plane(k, new Vector3(-215f, 0.45f, 790f), 0f, 1.5f);
            foreach (float hx in new[] { 180f, 340f })
            {
                var hrng = new List<List<Vector3>>();
                for (int i = 0; i <= 6; i++) hrng.Add(Section(new Vector3(hx, 0, 885f + i * 25f), Vector3.right, 70f, 32f, 12));
                Shell(k, hrng, (i, t) => t < 0.06f ? LM.Glass : LM.Metal, MetalW, GlassBlue, false, true);
                var door = Section(new Vector3(hx, 0, 885f), Vector3.right, 66f, 30f, 12);
                var c0 = new Vector3(hx, 0, 884.5f);
                for (int j = 0; j < 12; j++) k.Tri(c0, door[j] + Vector3.back * 0.5f, door[j + 1] + Vector3.back * 0.5f, Vector3.back, (j & 1) == 0 ? MetalG : MetalD, LM.Metal, 3f, Vector2.zero, Vector2.right, Vector2.up);
            }
            Plane(k, new Vector3(180f, 0.45f, 790f), 180f, 1.25f);
            // control tower: a slim tapering shaft, the glazed cab, the radar
            float twx = -20f, twz = 1110f;
            k.Prism(LandmarkKit.RoundRect(twx, twz, 56f, 30f, 8f, 3), 0.3f, 9f, GlassBlue, LM.Glass, 4.5f, White, LM.Roof);
            var shaft0 = LandmarkKit.Circle(twx, twz, 9f, 16); var shaft1 = LandmarkKit.Circle(twx, twz, 5.5f, 16);
            k.Loft(shaft0, 9f, shaft1, 76f, White, LM.Solid, 4f);
            k.Prism(LandmarkKit.Circle(twx, twz, 10.5f, 16), 76f, 78f, White, LM.Solid, 2f, White, LM.Roof);
            k.Loft(LandmarkKit.Circle(twx, twz, 10.5f, 16), 78f, LandmarkKit.Circle(twx, twz, 13f, 16), 87f, GlassDark, LM.Glass, 3f);
            k.Prism(LandmarkKit.Circle(twx, twz, 13.6f, 16), 87f, 88.4f, White, LM.Solid, 1.4f, MetalG, LM.Metal);
            k.Beam(new Vector3(twx, 88.4f, twz), new Vector3(twx, 98f, twz), 0.5f, 0.5f, MetalG, LM.Steel);
            k.Box(new Vector3(twx, 98.3f, twz), new Vector3(0.9f, 0.6f, 0.9f), 0, RedL, LM.Light, 1f, RedL, LM.Light);
            k.Box(new Vector3(twx, 81f, twz), new Vector3(27f, 0.4f, 27f), 0, Warm, LM.Light, 1f, Warm, -1);
            // fuel farm in its bund
            k.Prism(LandmarkKit.Rect(-320f, 1380f, 170f, 120f), 0.25f, 1.6f, Concrete, LM.Solid, 1f, Gravel, LM.Paving);
            for (int i = 0; i < 3; i++) for (int j = 0; j < 2; j++) k.Cylinder(new Vector3(-375f + i * 55f, 1.6f, 1350f + j * 60f), 15f, 14f, 20, White, LM.Metal, 3f, MetalW, LM.Metal, 1.5f);
            // fire station (rescue and firefighting) with red doors
            k.Prism(LandmarkKit.Rect(300f, 1300f, 80f, 34f), 0.3f, 9f, White, LM.Solid, 4.5f, Roof, LM.Roof);
            for (int i = 0; i < 5; i++) k.Box(new Vector3(268f + i * 16f, 3.5f, 1282.6f), new Vector3(10f, 6f, 0.6f), 0, Red, LM.Solid, 2f, Red, LM.Solid);
            k.Prism(LandmarkKit.Rect(348f, 1300f, 12f, 12f), 0.3f, 22f, White, LM.Solid, 4.5f, Roof, LM.Roof);

            // ---- landside: the road from the south-west gate, roundabout, boulevard to the forecourt loop at the nose, car parks, hotel
            var gate = new Vector2(-450f, -1900f); var rbC = new Vector2(-505f, -1805f);
            Road(k, new List<Vector2> { gate + new Vector2(0.5f, -0.866f) * 6f, rbC + new Vector2(0.5f, -0.866f) * 36f }, 7.5f, false);
            var ring = LandmarkKit.Circle(rbC.x, rbC.y, 36f, 28); Road(k, ring, 6.5f, true, false);
            k.Prism(LandmarkKit.Circle(rbC.x, rbC.y, 28f, 20), 0.3f, 0.6f, Stone, LM.Solid, 1f, Grass, LM.Plant);
            k.Tree(new Vector3(rbC.x, 0.6f, rbC.y), 12f, Leaf, 4f);
            // boulevard: two carriageways and a planted median
            Vector2 b1 = new Vector2(-125f, -1054f), b0 = rbC + (b1 - rbC).normalized * 40f, bd = (b1 - b0).normalized, bs = new Vector2(bd.y, -bd.x);
            Road(k, new List<Vector2> { b0 + bs * 10f, b1 + bs * 10f }, 5.6f, false); Road(k, new List<Vector2> { b0 - bs * 10f, b1 - bs * 10f }, 5.6f, false);
            { var mm = (b0 + b1) * 0.5f; float yaw = Mathf.Atan2(bd.x, bd.y) * Mathf.Rad2Deg; k.Prism(LandmarkKit.Rect(mm.x, mm.y, 8f, (b1 - b0).magnitude - 30f, yaw), 0.3f, 0.65f, Stone, LM.Solid, 1f, Grass, LM.Plant); }
            for (float s = 30f; s < (b1 - b0).magnitude - 20f; s += 26f)
            {
                var q = b0 + bd * s; k.Tree(new Vector3(q.x, 0.65f, q.y), 9f, (((int)s) & 1) == 0 ? Leaf : Leaf2, s * 0.1f);
                foreach (float sg in new[] { -1f, 1f }) { var e = q + bs * (sg * 22f); k.Tree(new Vector3(e.x, 0.3f, e.y), 8f, Leaf2, s * 0.07f + sg); }
            }
            // forecourt loop round the plaza; departures canopy over the kerb in front of the nose
            var loop = LandmarkKit.RoundRect(0, -975f, 320f, 170f, 60f, 6); Road(k, loop, 8f, true);
            k.Prism(LandmarkKit.RoundRect(0, -975f, 296f, 146f, 50f, 6), 0.25f, 0.5f, PaveDark, LM.Solid, 1f, Stone, LM.Paving);
            k.Prism(LandmarkKit.RoundRect(0, -985f, 150f, 50f, 22f, 4), 0.5f, 0.62f, Stone, LM.Solid, 1f, Water, LM.Water);
            Lawn(k, -105f, -985f, 60f, 90f, 18f); Lawn(k, 105f, -985f, 60f, 90f, 18f);
            Trees(k, -128f, -1020f, -84f, -950f, 15f, 9f, 6f); Trees(k, 84f, -1020f, 128f, -950f, 15f, 9f, 7f);
            k.Prism(LandmarkKit.Rect(0, -868f, 360f, 32f), 0.25f, 0.5f, PaveDark, LM.Solid, 1f, Pave, LM.Paving);       // kerb pavement
            k.Box(new Vector3(0, 14f, -878f), new Vector3(330f, 1.2f, 40f), 0, GlassBlue, LM.Glass, 1.2f, GlassBlue, LM.Glass);
            k.Box(new Vector3(0, 14.8f, -878f), new Vector3(334f, 0.5f, 42f), 0, White, LM.Solid, 0.5f, White, LM.Roof);
            for (int i = 0; i < 12; i++) foreach (float zz in new[] { -895f, -861f }) k.Beam(new Vector3(-150f + i * 27.3f, 0.5f, zz), new Vector3(-150f + i * 27.3f, 13.4f, zz), 0.9f, 0.9f, White, LM.Solid);
            // exit road from the loop back to the boulevard; the LRT skywalk to the canopy
            var exitR = new List<Vector2> { new Vector2(130f, -1053f), new Vector2(150f, -1095f), new Vector2(150f, -1560f) }; exitR.AddRange(Bez(new Vector2(150f, -1560f), new Vector2(150f, -1640f), new Vector2(60f, -1650f), new Vector2(-20f, -1650f), 8));
            exitR.Add(new Vector2(-405f, -1650f)); Road(k, exitR, 7f, false);
            k.Beam(new Vector3(172f, 10f, -990f), new Vector3(140f, 10f, -872f), 7f, 4.2f, GlassBlue, LM.Glass);
            k.Beam(new Vector3(172f, 12.2f, -990f), new Vector3(140f, 12.2f, -872f), 7.6f, 0.4f, White, LM.Roof);
            k.Beam(new Vector3(160f, 0.4f, -945f), new Vector3(160f, 8f, -945f), 1.2f, 1.2f, White, LM.Solid);
            // car parks: east (under the LRT), centre (taxis and short stay); a multi-storey car park and the hotel west of the boulevard
            CarPark(k, 175f, 420f, -1560f, -1180f, 11f);
            CarPark(k, -100f, 112f, -1560f, -1180f, 23f);
            for (int lv = 0; lv < 5; lv++)
            {
                float y0 = 0.3f + lv * 3.4f;
                k.Prism(LandmarkKit.Rect(-330f, -1170f, 140f, 110f), y0, y0 + 2.2f, GlassDark, LM.Solid, 2.2f, Concrete, -1);
                k.Prism(LandmarkKit.Rect(-330f, -1170f, 142f, 112f), y0 + 2.2f, y0 + 3.4f, Concrete, LM.Solid, 1.2f, Concrete, LM.Paving);
            }
            for (int i = 0; i < 6; i++) k.Box(new Vector3(-330f, 18.6f, -1210f + i * 16f), new Vector3(126f, 0.5f, 9f), 0, LM.C("#1d2d4a"), LM.Glass, 1f, LM.C("#24375a"), LM.Glass);     // solar canopies
            k.Prism(LandmarkKit.RoundRect(-300f, -980f, 76f, 30f, 6f, 3), 0.3f, 8f, GlassWarm, LM.Glass, 4f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Chamfer(-300f, -980f, 66f, 24f, 4f), 8f, 52f, GlassTeal, LM.Fins, 3.6f, Roof, LM.Roof);
            k.Box(new Vector3(-300f, 53f, -980f), new Vector3(40f, 2f, 14f), 0, MetalG, LM.Metal, 2f, Roof, LM.Roof);
            Trees(k, -40f, -1680f, 100f, -1680f, 20f, 8f, 8f);
            Trees(k, 430f, -1590f, 430f, -1100f, 22f, 8f, 9f);
        }

        // ------------------------------------------------------------------ L7 by Lotte: slim urban hotel, 26 floors
        static void HotelL7(LandmarkKit k)
        {
            Pad(k, 90f, 70f, 8f, Pave);
            k.Prism(LandmarkKit.RoundRect(0, 0, 70f, 48f, 6f, 3), 0.3f, 12f, GlassWarm, LM.Glass, 6f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Chamfer(4f, 4f, 40f, 22f, 3f), 12f, 96f, GlassDark, LM.Fins, 3.4f, Roof, LM.Roof);
            k.Box(new Vector3(-17f, 54f, 4f), new Vector3(3f, 84f, 23f), 0, White, LM.Solid, 3.4f, White, LM.Roof);
            k.Box(new Vector3(4f, 98f, 4f), new Vector3(30f, 4f, 16f), 0, MetalG, LM.Metal, 3f, Roof, LM.Roof);
            // red L7 sign on the crown
            k.Box(new Vector3(4f, 93f, 4f - 11.4f), new Vector3(10f, 4f, 0.6f), 0, Red, LM.Light, 1f, Red, LM.Light);
            Trees(k, -38f, -30f, 38f, -30f, 9.5f, 7f, 5f);
        }

        // ------------------------------------------------------------------ food plant (PepsiCo snacks / Mars petfood)
        static void FoodPlant(LandmarkKit k, Color32 brand, bool potato)
        {
            Pad(k, 430f, 300f, 10f, PaveDark);
            // production hall with roof lights and a brand band along the front
            k.Prism(LandmarkKit.Rect(-40f, 10f, 230f, 112f), 0.3f, 15f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
            for (int i = 0; i < 9; i++) k.Box(new Vector3(-140f + 25f + i * 25f, 15.6f, 10f), new Vector3(4f, 1.2f, 90f), 0, GlassBlue, LM.Glass, 1.2f, GlassBlue, LM.Glass);
            k.Box(new Vector3(-40f, 12.5f, 10f - 56.4f), new Vector3(230f, 2.6f, 0.8f), 0, brand, LM.Solid, 3f, brand, LM.Roof);
            k.Box(new Vector3(40f, 9f, 10f - 56.6f), new Vector3(9f, 9f, 0.6f), 0, brand, LM.Light, 1f, brand, LM.Light);
            // office and staff block, glazed
            k.Prism(LandmarkKit.RoundRect(-110f, -95f, 70f, 22f, 4f, 2), 0.3f, 13f, GlassBlue, LM.Glass, 4.2f, Roof, LM.Roof);
            k.Box(new Vector3(-110f, 13.8f, -95f), new Vector3(72f, 1.6f, 24f), 0, White, LM.Solid, 1.6f, White, LM.Roof);
            if (potato)
            {
                // raw potato stores: four long gabled halls
                for (int i = 0; i < 4; i++) Gable(k, 145f, -60f + i * 38f, 110f, 30f, 8f, 5f, MetalG, LM.Metal, LM.C("#8f9399"));
                Silos(k, 110f, 110f, 6, 4.5f, 24f, MetalW);
            }
            else
            {
                // feed mill tower and ingredient silos
                k.Box(new Vector3(120f, 21f, 30f), new Vector3(30f, 42f, 24f), 0, Concrete, LM.Solid, 4f, Roof, LM.Roof);
                Silos(k, 150f, -20f, 4, 6f, 32f, MetalW); Silos(k, 150f, 10f, 4, 6f, 32f, MetalW);
                k.Prism(LandmarkKit.Rect(120f, -95f, 90f, 50f), 0.3f, 12f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
            }
            k.Cylinder(new Vector3(60f, 0.3f, 75f), 1.6f, 40f, 12, Concrete, LM.Solid, 4f, Steel, LM.Steel);
            // utilities: tanks and the truck yard
            for (int i = 0; i < 3; i++) k.Cylinder(new Vector3(-185f + i * 17f, 0.3f, 100f), 7f, 11f, 18, MetalW, LM.Metal, 3f, MetalG, LM.Metal, 1.2f);
            k.Prism(LandmarkKit.Rect(40f, -100f, 120f, 50f), 0.3f, 0.36f, Asph, LM.Paving, 3f, Asph, LM.Paving);
            for (int i = 0; i < 7; i++) Truck(k, new Vector3(-12f + i * 16f, 0.3f, -112f), 90f, i % 3 == 0 ? brand : White);
            Cars(k, -170f, -135f, 22, 3, 3f);
            Trees(k, -205f, -142f, 205f, -142f, 12f, 7f, 7f);
        }

        // ------------------------------------------------------------------ paper mill (tissue / paper machines)
        static void PaperMill(LandmarkKit k)
        {
            Pad(k, 440f, 280f, 10f, PaveDark);
            k.Prism(LandmarkKit.Rect(-20f, 20f, 280f, 50f), 0.3f, 24f, MetalW, LM.Metal, 4f, Roof, LM.Roof);           // machine hall
            k.Prism(LandmarkKit.Rect(-20f, -40f, 200f, 70f), 0.3f, 14f, MetalG, LM.Metal, 4f, Roof, LM.Roof);          // finished goods
            k.Box(new Vector3(-20f, 21f, 20f - 25.4f), new Vector3(280f, 2.4f, 0.6f), 0, LM.C("#2e7d4f"), LM.Solid, 3f, LM.C("#2e7d4f"), LM.Roof);
            for (int i = 0; i < 4; i++) k.Cylinder(new Vector3(150f + (i % 2) * 22f, 0.3f, 60f + (i / 2) * 22f), 9f, 18f, 20, Concrete, LM.Solid, 4f, MetalG, LM.Metal, 1.5f);
            k.Cylinder(new Vector3(160f, 0.3f, -40f), 2.4f, 62f, 14, LM.C("#d8d4cc"), LM.Solid, 4f, Steel, LM.Steel);
            k.Box(new Vector3(160f, 56f, -40f), new Vector3(5.2f, 3f, 5.2f), 0, Red, LM.Solid, 3f, Red, LM.Roof);
            k.Prism(LandmarkKit.Rect(-140f, 90f, 120f, 40f), 0.3f, 10f, MetalG, LM.Metal, 4f, Roof, LM.Roof);            // pulp / bale store
            k.Prism(LandmarkKit.RoundRect(-170f, -100f, 60f, 20f, 3f, 2), 0.3f, 11f, GlassBlue, LM.Glass, 3.6f, Roof, LM.Roof);
            for (int i = 0; i < 8; i++) Truck(k, new Vector3(-100f + i * 17f, 0.3f, -96f), 90f, White);
            Cars(k, 60f, -125f, 18, 2, 11f);
        }

        // ------------------------------------------------------------------ flexible packaging plant
        static void Packaging(LandmarkKit k)
        {
            Pad(k, 300f, 200f, 10f, PaveDark);
            k.Prism(LandmarkKit.Rect(-10f, 15f, 170f, 86f), 0.3f, 13f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
            for (int i = 0; i < 6; i++) k.Box(new Vector3(-80f + i * 28f, 13.5f, 15f), new Vector3(3.5f, 1f, 70f), 0, GlassBlue, LM.Glass, 1f, GlassBlue, LM.Glass);
            k.Box(new Vector3(-10f, 10.8f, 15f - 43.4f), new Vector3(170f, 2f, 0.6f), 0, LM.C("#7a2d8c"), LM.Solid, 3f, LM.C("#7a2d8c"), LM.Roof);
            k.Prism(LandmarkKit.RoundRect(-95f, -62f, 48f, 18f, 3f, 2), 0.3f, 10f, GlassBlue, LM.Glass, 3.4f, Roof, LM.Roof);
            Silos(k, 95f, 60f, 3, 3.2f, 16f, MetalW);
            for (int i = 0; i < 5; i++) Truck(k, new Vector3(20f + i * 15f, 0.3f, -60f), 90f, White);
            Cars(k, -130f, -88f, 14, 2, 21f);
        }

        // ------------------------------------------------------------------ logistics park: class A warehouses with dock doors and truck courts
        static void Logistics(LandmarkKit k, int halls, float L, float D)
        {
            float span = D + 70f; Pad(k, L + 80f, halls * span + 60f, 10f, Asph);
            for (int h = 0; h < halls; h++)
            {
                float cz = (h - (halls - 1) * 0.5f) * span;
                k.Prism(LandmarkKit.Rect(0, cz, L, D), 0.3f, 14f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
                k.Box(new Vector3(0, 13.2f, cz - D * 0.5f - 0.3f), new Vector3(L, 1.6f, 0.4f), 0, LM.C("#e0261b"), LM.Solid, 3f, Red, LM.Roof);
                int doors = Mathf.FloorToInt(L / 8f) - 4;
                for (int i = 0; i < doors; i++)
                {
                    float x = -L * 0.5f + 16f + i * 8f;
                    k.Box(new Vector3(x, 2.6f, cz - D * 0.5f - 0.25f), new Vector3(3f, 3.2f, 0.3f), 0, Steel, LM.Steel, 1f, Steel, LM.Steel);
                    if ((i * 7) % 3 == 0) Truck(k, new Vector3(x, 0.3f, cz - D * 0.5f - 9f), 90f, (i % 5 == 0) ? LM.C("#2f4f7a") : White);
                }
                k.Prism(LandmarkKit.RoundRect(-L * 0.5f + 20f, cz + D * 0.5f + 8f, 34f, 14f, 3f, 2), 0.3f, 9f, GlassBlue, LM.Glass, 3.4f, Roof, LM.Roof);
            }
            Cars(k, L * 0.5f - 60f, halls * span * 0.5f + 2f, 18, 2, 31f);
        }

        // ------------------------------------------------------------------ rail-road terminal (TLC Zhetygen): sidings, gantry cranes, container stacks
        static void RailTerminal(LandmarkKit k)
        {
            Pad(k, 520f, 220f, 8f, Gravel, LM.Roof);
            for (int r = 0; r < 4; r++)
            {
                float z = -60f + r * 6f;
                k.Beam(new Vector3(-250f, 0.55f, z - 0.75f), new Vector3(250f, 0.55f, z - 0.75f), 0.15f, 0.18f, Steel, LM.Steel);
                k.Beam(new Vector3(-250f, 0.55f, z + 0.75f), new Vector3(250f, 0.55f, z + 0.75f), 0.15f, 0.18f, Steel, LM.Steel);
                // a train of flat wagons with containers on two of the sidings
                if (r % 2 == 0) for (int w = 0; w < 16; w++)
                {
                    float x = -200f + w * 15.5f;
                    k.Box(new Vector3(x, 1.3f, z), new Vector3(14.5f, 0.9f, 2.6f), 0, Steel, LM.Steel, 1f, Steel, LM.Steel);
                    Color32 cc = (w * 5 + r) % 4 == 0 ? LM.C("#b5442c") : (w * 5 + r) % 4 == 1 ? LM.C("#2f5d8a") : (w * 5 + r) % 4 == 2 ? LM.C("#d9d4c7") : LM.C("#3f7a4f");
                    k.Box(new Vector3(x, 3.05f, z), new Vector3(12.2f, 2.6f, 2.44f), 0, cc, LM.Metal, 3f, cc, LM.Metal);
                }
            }
            // container stacks
            for (int i = 0; i < 14; i++) for (int j = 0; j < 6; j++)
            {
                int hgt = 1 + (i * 3 + j * 7) % 3;
                Color32 cc = (i + j * 3) % 5 == 0 ? LM.C("#b5442c") : (i + j * 3) % 5 == 1 ? LM.C("#2f5d8a") : (i + j * 3) % 5 == 2 ? LM.C("#d9d4c7") : (i + j * 3) % 5 == 3 ? LM.C("#3f7a4f") : LM.C("#c58b2a");
                k.Box(new Vector3(-160f + i * 13.5f, 0.3f + hgt * 1.3f, -12f + j * 3.1f), new Vector3(12.2f, hgt * 2.6f, 2.44f), 0, cc, LM.Metal, 2.6f, cc, LM.Metal);
            }
            // two rail-mounted gantry cranes over sidings and stacks
            for (int g = 0; g < 2; g++)
            {
                float x = -60f + g * 110f; var col = LM.C("#e8b52a");
                for (int s = -1; s <= 1; s += 2)
                {
                    k.Beam(new Vector3(x + s * 9f, 0.3f, -66f), new Vector3(x + s * 9f, 24f, -66f), 1.1f, 1.1f, col, LM.Metal);
                    k.Beam(new Vector3(x + s * 9f, 0.3f, 10f), new Vector3(x + s * 9f, 24f, 10f), 1.1f, 1.1f, col, LM.Metal);
                    k.Beam(new Vector3(x + s * 9f, 24f, -70f), new Vector3(x + s * 9f, 24f, 14f), 1.4f, 1.8f, col, LM.Metal);
                }
                k.Box(new Vector3(x, 22f, -40f), new Vector3(20f, 2.2f, 5f), 0, col, LM.Metal, 2f, col, LM.Metal);
            }
            k.Prism(LandmarkKit.Rect(120f, 60f, 180f, 60f), 0.3f, 13f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
            k.Prism(LandmarkKit.RoundRect(-200f, 70f, 46f, 16f, 3f, 2), 0.3f, 10f, GlassBlue, LM.Glass, 3.4f, Roof, LM.Roof);
            for (int i = 0; i < 8; i++) Truck(k, new Vector3(40f + i * 16f, 0.3f, 22f), 90f, i % 2 == 0 ? White : LM.C("#2f5d8a"));
        }

        // ------------------------------------------------------------------ 220/110 kV substation
        static void Substation(LandmarkKit k)
        {
            Pad(k, 180f, 140f, 4f, Gravel, LM.Roof);
            // fence
            var f = LandmarkKit.Rect(0, 0, 172f, 132f);
            for (int i = 0; i < 4; i++) { var a = f[i]; var b = f[(i + 1) % 4]; k.Beam(new Vector3(a.x, 1.3f, a.y), new Vector3(b.x, 1.3f, b.y), 0.12f, 2.2f, MetalD, LM.Steel); }
            // transformers (bodies, radiators, bushings)
            for (int i = 0; i < 4; i++)
            {
                float x = -45f + i * 30f;
                k.Box(new Vector3(x, 3.3f, -10f), new Vector3(9f, 6f, 6f), 0, LM.C("#8c949c"), LM.Metal, 2f, LM.C("#7c838a"), LM.Metal);
                k.Box(new Vector3(x, 3f, -15f), new Vector3(8f, 5f, 2.4f), 0, LM.C("#7c838a"), LM.Metal, 1f, LM.C("#7c838a"), LM.Metal);
                for (int b = -1; b <= 1; b++) k.Cylinder(new Vector3(x + b * 2.5f, 6.3f, -10f), 0.35f, 3.2f, 8, LM.C("#cfd3d6"), LM.Solid, 1f, LM.C("#cfd3d6"), LM.Solid);
            }
            // gantry portals and busbars
            for (int i = 0; i < 6; i++)
            {
                float x = -70f + i * 28f;
                k.Beam(new Vector3(x, 0.3f, 20f), new Vector3(x, 18f, 20f), 0.7f, 0.7f, MetalG, LM.Steel);
                k.Beam(new Vector3(x, 0.3f, 50f), new Vector3(x, 18f, 50f), 0.7f, 0.7f, MetalG, LM.Steel);
                k.Beam(new Vector3(x, 18f, 19f), new Vector3(x, 18f, 51f), 0.6f, 0.8f, MetalG, LM.Steel);
            }
            k.Beam(new Vector3(-72f, 14f, 30f), new Vector3(72f, 14f, 30f), 0.25f, 0.25f, MetalG, LM.Steel);
            k.Beam(new Vector3(-72f, 14f, 40f), new Vector3(72f, 14f, 40f), 0.25f, 0.25f, MetalG, LM.Steel);
            k.Prism(LandmarkKit.Rect(55f, -45f, 36f, 16f), 0.3f, 7f, White, LM.Solid, 3.5f, Roof, LM.Roof);
        }

        // ------------------------------------------------------------------ gas-turbine power plant 2 × 250 MW (H2-ready)
        static void PowerPlant(LandmarkKit k)
        {
            Pad(k, 340f, 240f, 8f, PaveDark);
            for (int u = 0; u < 2; u++)
            {
                float z = -45f + u * 80f;
                k.Prism(LandmarkKit.Rect(-70f, z, 90f, 38f), 0.3f, 28f, MetalW, LM.Metal, 4f, Roof, LM.Roof);           // turbine hall
                k.Prism(LandmarkKit.Rect(10f, z, 60f, 26f), 0.3f, 32f, MetalG, LM.Metal, 4f, Roof, LM.Roof);            // HRSG
                k.Cylinder(new Vector3(52f, 0.3f, z), 4f, 60f, 16, LM.C("#cfd2d4"), LM.Metal, 4f, Steel, LM.Steel);
                k.Box(new Vector3(52f, 57f, z), new Vector3(8.6f, 2.4f, 8.6f), 0, Red, LM.Solid, 2f, Red, LM.Roof);
            }
            // air-cooled condenser: a deck of fans on legs
            k.Box(new Vector3(115f, 18f, -5f), new Vector3(70f, 4f, 120f), 0, MetalG, LM.Metal, 2f, Steel, LM.Steel);
            for (int i = 0; i < 4; i++) for (int j = 0; j < 7; j++) k.Cylinder(new Vector3(92f + i * 15f, 20f, -55f + j * 16.5f), 5.5f, 1.4f, 16, MetalW, LM.Metal, 1f, Steel, LM.Steel);
            for (int i = 0; i < 4; i++) for (int j = 0; j < 4; j++) k.Beam(new Vector3(85f + i * 20f, 0.3f, -60f + j * 36f), new Vector3(85f + i * 20f, 16f, -60f + j * 36f), 1.2f, 1.2f, Concrete, LM.Solid);
            for (int i = 0; i < 2; i++) k.Cylinder(new Vector3(-140f, 0.3f, -60f + i * 30f), 10f, 14f, 20, MetalW, LM.Metal, 3f, MetalG, LM.Metal, 1.5f);
            k.Prism(LandmarkKit.Rect(-120f, 85f, 50f, 20f), 0.3f, 10f, GlassBlue, LM.Glass, 3.6f, Roof, LM.Roof);
        }

        // ------------------------------------------------------------------ university campus (KAIST Kazakhstan), after the KAIST campus in Daejeon:
        // a park campus — lawns, alleys and a lake with an island and fountains laid out first (green from the start of the works), the
        // main hall in the manner of the Academic Cultural Complex (a blue glass box with a white grid of mullions lifted on white columns
        // over a recessed lobby, a white terrace with a stair and a ramp, glass pyramid roof lights, a reflecting pool with jets in front),
        // the library and research tower B1 with a sloping west face, white floor bands, vertical fins and a glass pyramid on a roof garden,
        // the laboratories as a comb of teal-glass wings with green roofs around planted courts, the curved north teaching block, the
        // athletics oval with a stand. Only the aprons of the buildings are an earth site while they are built.
        static readonly Color32 CampusBlue = LM.C("#25557e"), SkyGlass = LM.C("#4f86ad"), Pond = LM.C("#2c5d63"), Track = LM.C("#b3573f"),
            CampusTurf = LM.C("#4f8a43"), Spray = LM.C("#eef7fc"), HedgeG = LM.C("#46683a"), Rim = LM.C("#d8d3c8");
        const float GT = LandmarkKit.GreenTag;

        static List<Vector2> Ellipse(float cx, float cz, float rx, float rz, int seg, float wob = 0f, float ph = 0f)
        {
            var l = new List<Vector2>();
            for (int s = 0; s < seg; s++)
            {
                float a = s * 2f * Mathf.PI / seg, f = 1f + wob * Mathf.Sin(a * 3f + ph) + wob * 0.6f * Mathf.Sin(a * 5f + ph * 1.7f);
                l.Add(new Vector2(cx + Mathf.Cos(a) * rx * f, cz + Mathf.Sin(a) * rz * f));
            }
            return l;
        }
        /// <summary>A band between two outlines with the same number of corners (a rim, a ring path, a walk along the edge).</summary>
        static void Band(LandmarkKit k, List<Vector2> inner, List<Vector2> outer, float y0, float y1, Color32 side, Color32 top, int topMat, float prm)
        {
            for (int i = 0; i < inner.Count; i++)
            {
                int j = (i + 1) % inner.Count;
                k.Prism(new List<Vector2> { inner[i], inner[j], outer[j], outer[i] }, y0, y1, side, LM.Solid, prm, top, topMat, false, prm);
            }
        }
        /// <summary>A straight path a → b, w wide, paving on a low stone kerb.</summary>
        static void Walk(LandmarkKit k, Vector2 a, Vector2 b, float w, float prm = GT, float y1 = 0.45f)
        {
            var d = (b - a).normalized; var n = new Vector2(-d.y, d.x) * (w * 0.5f);
            k.Prism(new List<Vector2> { a - n, b - n, b + n, a + n }, 0.3f, y1, Rim, LM.Solid, prm, Pave, LM.Paving, false, prm);
        }
        /// <summary>A fountain jet from (x, y, z), h high; tall ones drop a crown of spray around them.</summary>
        static void Jet(LandmarkKit k, float x, float z, float y, float h, float prm)
        {
            float r = Mathf.Clamp(h * 0.045f, 0.12f, 0.75f);
            k.Tube(new Vector3(x, y, z), new Vector3(x, y + h, z), r, r * 0.3f, 6, Spray, LM.Light, true, prm);
            if (h < 6f) return;
            var top = new Vector3(x, y + h * 0.82f, z);
            for (int i = 0; i < 6; i++)
            {
                float a = (i * 60f + 15f) * Mathf.Deg2Rad; var dir = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                var mid = new Vector3(x, y + h * 0.62f, z) + dir * (h * 0.2f); var end = new Vector3(x, y + 0.1f, z) + dir * (h * 0.3f);
                k.Tube(top, mid, r * 0.45f, r * 0.35f, 5, Spray, LM.Light, false, prm);
                k.Tube(mid, end, r * 0.35f, r * 0.12f, 5, Spray, LM.Light, false, prm);
            }
        }
        static void Lamp(LandmarkKit k, float x, float z)
        {
            k.Prism(LandmarkKit.Rect(x, z, 0.22f, 0.22f), 0.3f, 4.3f, Steel, LM.Steel, GT, Steel, -1);
            k.Prism(LandmarkKit.Rect(x, z, 0.7f, 0.7f), 4.3f, 4.7f, Warm, LM.Light, GT, Warm, LM.Light, false, GT);
        }
        static void ParkTree(LandmarkKit k, float x, float z, float h, float seed)
        {
            k.Planted = true; k.Tree(new Vector3(x, 0.4f, z), h, (Mathf.FloorToInt(seed * 7f) & 1) == 0 ? Leaf : Leaf2, seed); k.Planted = false;
        }
        static float Hash(float x, float z) => Mathf.Repeat(Mathf.Sin(x * 12.9898f + z * 78.233f) * 43758.5453f, 1f);
        /// <summary>A sector of a ring (centre c, radii r0..r1, angles a0..a1 in degrees) as a four-corner footprint.</summary>
        static List<Vector2> Sector(Vector2 c, float r0, float r1, float a0, float a1)
        {
            float b0 = a0 * Mathf.Deg2Rad, b1 = a1 * Mathf.Deg2Rad;
            Vector2 d0 = new Vector2(Mathf.Cos(b0), Mathf.Sin(b0)), d1 = new Vector2(Mathf.Cos(b1), Mathf.Sin(b1));
            return new List<Vector2> { c + d0 * r0, c + d1 * r0, c + d1 * r1, c + d0 * r1 };
        }

        static void Campus(LandmarkKit k)
        {
            // ---- the ground: one lawn over the whole plot (a plinth buried in the slope), a walk and a double alley round the edge
            // (part 6 = the park of LandmarkData's KAIST campus: built first, in a few months, on its own windows — Wbs.P*)
            k.Part = 6; W(k, Wbs.PGround, 0f, 0.4f);
            k.Prism(LandmarkKit.RoundRect(0, 0, 420f, 360f, 30f, 5), -16f, 0.3f, PaveDark, LM.Solid, GT, Grass, LM.Plant, false, GT);
            W(k, Wbs.PPaths, 0f, 0.5f);
            Band(k, LandmarkKit.RoundRect(0, 0, 392f, 332f, 20f, 5), LandmarkKit.RoundRect(0, 0, 402f, 342f, 25f, 5), 0.3f, 0.45f, Rim, Pave, LM.Paving, GT);

            // ---- the lake with an island, a footbridge and fountains; a ring path with lamps round it
            Vector2 lc = new Vector2(-15f, -5f); float lrx = 64f, lrz = 36f;
            var shore = Ellipse(lc.x, lc.y, lrx, lrz, 40, 0.05f, 0.7f);
            W(k, Wbs.PLake, 0f, 0.6f);
            k.Prism(shore, 0.15f, 0.34f, Rim, LM.Solid, GT, Pond, LM.Water, false, GT);
            Band(k, shore, Ellipse(lc.x, lc.y, lrx + 1.8f, lrz + 1.8f, 40, 0.05f, 0.7f), 0.3f, 0.55f, Rim, Rim, LM.Paving, GT);
            W(k, Wbs.PPaths, 0f, 0.5f);
            Band(k, Ellipse(lc.x, lc.y, lrx + 10f, lrz + 10f, 48), Ellipse(lc.x, lc.y, lrx + 14f, lrz + 14f, 48), 0.3f, 0.45f, Rim, Pave, LM.Paving, GT);
            W(k, Wbs.PLamps, 0f, 5f);
            for (int i = 0; i < 18; i++) { float a = (i + 0.5f) * 20f * Mathf.Deg2Rad; Lamp(k, lc.x + Mathf.Cos(a) * (lrx + 16f), lc.y + Mathf.Sin(a) * (lrz + 16f)); }
            W(k, Wbs.PLake, 0f, 0.9f);
            k.Prism(Ellipse(8f, 10f, 13f, 8.5f, 18, 0.08f, 2.1f), 0.2f, 0.85f, GrassDark, LM.Solid, GT, Grass, LM.Plant, false, GT);
            W(k, Wbs.PTrees, 0f, 12f);
            ParkTree(k, 4f, 10f, 11f, 0.31f); ParkTree(k, 12f, 13f, 9.5f, 0.57f); ParkTree(k, 10f, 6f, 8f, 0.83f);
            W(k, Wbs.PPaths, 0f, 2.2f);
            k.Prism(LandmarkKit.Rect(8f, 26f, 3.2f, 18f), 0.3f, 1.05f, White, LM.Solid, GT, Stone, LM.Paving, false, GT);            // footbridge to the island
            k.Beam(new Vector3(6.4f, 2.0f, 17f), new Vector3(6.4f, 2.0f, 35f), 0.12f, 0.12f, White, LM.Solid, GT);
            k.Beam(new Vector3(9.6f, 2.0f, 17f), new Vector3(9.6f, 2.0f, 35f), 0.12f, 0.12f, White, LM.Solid, GT);
            W(k, Wbs.PLamps, 0f, 18.5f);
            Jet(k, -44f, -6f, 0.34f, 18f, GT);
            for (int i = 0; i < 5; i++) Jet(k, 14f + i * 6f, -12f + (i % 2) * 3f, 0.34f, 5.5f + (i == 2 ? 2.5f : 0f), GT);
            for (int i = 0; i < 6; i++) { float a = i * 60f * Mathf.Deg2Rad; Jet(k, -44f + Mathf.Cos(a) * 9f, -6f + Mathf.Sin(a) * 6f, 0.34f, 4f, GT); }

            // ---- main hall: a blue glass box with a white grid, lifted on white columns over a recessed lobby
            // (parts of the model = the buildings of LandmarkData's KAIST campus: 1 tower B1, 2 main hall, 3 laboratories, 4 north block, 5 sports)
            k.Part = 2;
            float mx = -20f, mz = -122f, mw = 150f, md = 56f;
            W(k, Wbs.MApron, 0f, 0.4f);
            k.Prism(LandmarkKit.RoundRect(mx, mz, mw + 22f, md + 22f, 6f, 3), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);   // apron (an earth site while built)
            W(k, Wbs.MLobby, 0.3f, 9f);
            k.Prism(LandmarkKit.RoundRect(mx, mz - 2f, mw - 30f, md - 16f, 4f, 3), 0.3f, 9f, GlassDark, LM.Glass, 4.4f, Roof, -1);    // lobby
            W(k, Wbs.MCols, 0.38f, 9.1f);
            for (int i = 0; i <= 12; i++) for (int s = 0; s < 2; s++)
                k.Cylinder(new Vector3(mx - mw * 0.5f + 4f + i * (mw - 8f) / 12f, 0.38f, mz + (s == 0 ? -1 : 1) * (md * 0.5f - 3f)), 0.75f, 8.7f, 10, White, LM.Solid, 3f, White, -1);
            W(k, Wbs.MSlab, 9f, 10.2f);
            k.Prism(LandmarkKit.Rect(mx, mz, mw + 2f, md + 2f), 9f, 10.2f, White, LM.Solid, 1.2f, Pave, LM.Paving, true);             // soffit and deck of the transfer slab
            W(k, Wbs.MBox, 10.2f, 28f);
            k.Prism(LandmarkKit.Rect(mx, mz, mw, md), 10.2f, 28f, CampusBlue, LM.Glass, 4.45f, Roof, LM.Roof);
            W(k, Wbs.MRoof, 28f, 29.2f);
            k.Prism(LandmarkKit.Rect(mx, mz, mw + 2f, md + 2f), 28f, 29.2f, White, LM.Solid, 1.2f, White, LM.Roof);                    // cornice
            W(k, Wbs.MGrid, 10.2f, 28f);
            float hx = mw * 0.5f + 0.3f, hz = md * 0.5f + 0.3f;
            for (int i = 0; i <= 20; i++)
            {
                float x = mx - mw * 0.5f + i * mw / 20f;
                k.Beam(new Vector3(x, 10.2f, mz - hz), new Vector3(x, 28f, mz - hz), 0.55f, 0.5f, White, LM.Solid, 1f);
                k.Beam(new Vector3(x, 10.2f, mz + hz), new Vector3(x, 28f, mz + hz), 0.55f, 0.5f, White, LM.Solid, 1f);
            }
            for (int i = 1; i < 8; i++)
            {
                float z = mz - md * 0.5f + i * md / 8f;
                k.Beam(new Vector3(mx - hx, 10.2f, z), new Vector3(mx - hx, 28f, z), 0.5f, 0.55f, White, LM.Solid, 1f);
                k.Beam(new Vector3(mx + hx, 10.2f, z), new Vector3(mx + hx, 28f, z), 0.5f, 0.55f, White, LM.Solid, 1f);
            }
            for (int f = 1; f < 4; f++)
            {
                float y = 10.2f + f * 4.45f;
                k.Beam(new Vector3(mx - hx, y, mz - hz), new Vector3(mx + hx, y, mz - hz), 0.5f, 0.45f, White, LM.Solid, 1f);
                k.Beam(new Vector3(mx - hx, y, mz + hz), new Vector3(mx + hx, y, mz + hz), 0.5f, 0.45f, White, LM.Solid, 1f);
                k.Beam(new Vector3(mx - hx, y, mz - hz), new Vector3(mx - hx, y, mz + hz), 0.5f, 0.45f, White, LM.Solid, 1f);
                k.Beam(new Vector3(mx + hx, y, mz - hz), new Vector3(mx + hx, y, mz + hz), 0.5f, 0.45f, White, LM.Solid, 1f);
            }
            // glass pyramid roof lights: a large one over the atrium, two small ones
            float[,] pyr = { { 0f, 44f, 26f, 10f }, { -46f, 16f, 16f, 6f }, { 44f, 16f, 16f, 6f } };
            W(k, Wbs.MRoof, 29.2f, 39.8f);
            for (int i = 0; i < 3; i++)
            {
                float px = mx + pyr[i, 0], w = pyr[i, 1], d = pyr[i, 2], h = pyr[i, 3], y0 = 29.2f;
                k.Prism(LandmarkKit.Rect(px, mz, w + 2f, d + 2f), y0, y0 + 0.6f, White, LM.Solid, 1f, White, LM.Roof);
                k.Loft(LandmarkKit.Rect(px, mz, w, d), y0 + 0.6f, LandmarkKit.Rect(px, mz, w * 0.02f, d * 0.02f), y0 + 0.6f + h, SkyGlass, LM.Glass, 2.2f);
                var ap = new Vector3(px, y0 + 0.6f + h, mz);
                for (int c = 0; c < 4; c++) k.Beam(new Vector3(px + (c % 2 == 0 ? -1 : 1) * w * 0.5f, y0 + 0.6f, mz + (c < 2 ? -1 : 1) * d * 0.5f), ap, 0.35f, 0.35f, White, LM.Solid, 1f);
            }
            // the white terrace along the front, a broad stair down to the plaza, a ramp at the west end
            float tz = mz + md * 0.5f + 5f;
            W(k, Wbs.MTerr, 0.3f, 5.5f);
            k.Prism(LandmarkKit.Rect(mx, tz, 124f, 10f), 0.3f, 4.2f, White, LM.Solid, 1.3f, Stone, LM.Paving);
            for (int i = 0; i < 8; i++)
                k.Prism(LandmarkKit.Rect(mx, tz + 5f + 0.75f + i * 1.5f, 32f, 1.5f), 0.3f, 4.2f - (i + 1) * 0.49f, White, LM.Solid, 0.5f, Stone, LM.Paving);
            float rx0 = mx - 62f, rz = tz;
            k.Slab(new Vector3(rx0, 4.0f, rz - 3f), new Vector3(rx0 - 34f, 0.5f, rz - 3f), new Vector3(rx0 - 34f, 0.5f, rz + 3f), new Vector3(rx0, 4.0f, rz + 3f), 0.5f, White, LM.Solid);
            k.Beam(new Vector3(rx0, 5.2f, rz - 3f), new Vector3(rx0 - 34f, 1.7f, rz - 3f), 0.25f, 0.25f, White, LM.Solid);
            k.Beam(new Vector3(rx0, 5.2f, rz + 3f), new Vector3(rx0 - 34f, 1.7f, rz + 3f), 0.25f, 0.25f, White, LM.Solid);
            k.Beam(new Vector3(mx - 62f, 5.2f, tz + 5f), new Vector3(mx - 16f, 5.2f, tz + 5f), 0.2f, 0.25f, White, LM.Solid);   // terrace rail
            k.Beam(new Vector3(mx + 16f, 5.2f, tz + 5f), new Vector3(mx + 62f, 5.2f, tz + 5f), 0.2f, 0.25f, White, LM.Solid);
            // the plaza with a reflecting pool and a row of jets, hedges and trees on its sides (finished with the landscaping)
            float pz = tz + 5f + 12f + 10f;
            W(k, Wbs.MPlaza, 0.3f, 9f);
            k.Prism(LandmarkKit.Rect(mx, pz, 150f, 20f), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Rect(mx, pz, 96f, 10f), 0.3f, 0.75f, Rim, LM.Solid, 1f, Rim, LM.Paving);
            k.Prism(LandmarkKit.Rect(mx, pz, 93f, 7f), 0.3f, 0.62f, Rim, LM.Solid, 1f, Pond, LM.Water);
            for (int i = 0; i < 12; i++) Jet(k, mx - 41.25f + i * 7.5f, pz, 0.62f, 3.2f, LandmarkKit.TreeTag);
            for (int s = -1; s <= 1; s += 2)
            {
                k.Prism(LandmarkKit.Rect(mx + s * 64f, pz, 16f, 1.4f), 0.38f, 1.4f, HedgeG, LM.Plant, LandmarkKit.TreeTag, HedgeG, LM.Plant, false, LandmarkKit.TreeTag);
                for (int i = 0; i < 3; i++) k.Tree(new Vector3(mx + s * (58f + i * 6f), 0.4f, pz + 5.5f), 8.5f, Leaf2, 0.2f + i * 0.17f + s);
            }

            // ---- library and research tower B1: the floors follow the tower profile (the interior and the monitoring use the same plates)
            k.Part = 1; k.NoWin();
            var keepP = IconicShape.P; IconicShape.P = TowerProfile.Kaist;
            try
            {
                float Xr = IconicShape.Xr, Cz = IconicShape.Cz, top = IconicShape.Roof, cx = Xr - IconicShape.RawWidth(top) * 0.5f;
                k.Prism(LandmarkKit.RoundRect(Xr - 22f, Cz, 84f, 74f, 6f, 3), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);   // apron
                for (int i = 0; i < IconicShape.Levels; i++)
                {
                    float y0 = IconicShape.FloorY(i), y1 = i == IconicShape.Levels - 1 ? top : IconicShape.FloorY(i + 1);
                    k.Loft(IconicShape.Ring(y0), y0, IconicShape.Ring(y1), y1, i == 0 ? GlassDark : GlassTeal, LM.Glass, IconicShape.Fh);
                    if (i > 0) k.Prism(IconicShape.Inset(y0, -0.45f), y0 - 0.3f, y0 + 0.35f, White, LM.Solid, 0.65f, White, -1);   // white floor band
                }
                k.Prism(IconicShape.Inset(top, -0.45f), top - 0.3f, top + 1.3f, White, LM.Solid, 1.6f, White, LM.Roof);            // parapet and roof
                k.Prism(IconicShape.Inset(top, 3.5f), top + 1.3f, top + 1.75f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);           // roof garden
                k.Prism(LandmarkKit.Rect(cx, Cz, 15f, 15f), top + 1.3f, top + 2f, White, LM.Solid, 1f, White, LM.Roof);
                k.Loft(LandmarkKit.Rect(cx, Cz, 14f, 14f), top + 2f, LandmarkKit.Rect(cx, Cz, 0.3f, 0.3f), top + 11f, SkyGlass, LM.Glass, 2.2f);
                for (int c = 0; c < 4; c++) k.Beam(new Vector3(cx + (c % 2 == 0 ? -7f : 7f), top + 2f, Cz + (c < 2 ? -7f : 7f)), new Vector3(cx, top + 11f, Cz), 0.3f, 0.3f, White, LM.Solid, 1f);
                // vertical white fins on the straight east face, a canopy over the west entrance
                float d0 = IconicShape.D0 * 0.5f - IconicShape.P.Chamfer - 0.5f;
                for (float z = -d0; z <= d0 + 0.01f; z += 2.5f) k.Beam(new Vector3(Xr + 0.45f, 0.3f, Cz + z), new Vector3(Xr + 0.45f, top + 1.3f, Cz + z), 0.25f, 0.9f, White, LM.Solid, 1f);
                float wx = Xr - IconicShape.RawWidth(5f);
                k.Prism(LandmarkKit.Rect(wx - 8.5f, Cz, 18f, 14f), 5.2f, 5.8f, White, LM.Solid, 1f, White, LM.Roof, true);
                k.Beam(new Vector3(wx - 16f, 0.38f, Cz - 6f), new Vector3(wx - 16f, 5.2f, Cz - 6f), 0.5f, 0.5f, White, LM.Solid);
                k.Beam(new Vector3(wx - 16f, 0.38f, Cz + 6f), new Vector3(wx - 16f, 5.2f, Cz + 6f), 0.5f, 0.5f, White, LM.Solid);
                foreach (float x in new[] { 120f, 132f, 168f, 180f }) k.Tree(new Vector3(x, 0.4f, Cz - 30f), 9f, Leaf, x * 0.013f);
            }
            finally { IconicShape.P = keepP; }

            // ---- laboratories: a spine with three teal-glass wings (stepped, with green roofs) around planted courts
            k.Part = 3;
            W(k, Wbs.Apron, 0f, 0.4f);
            k.Prism(LandmarkKit.Rect(-178f, 25f, 32f, 204f), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);
            W(k, Wbs.LSpine, 0.3f, 18.6f);
            k.Prism(LandmarkKit.Rect(-178f, 25f, 22f, 190f), 0.3f, 17f, GlassTeal, LM.Fins, 4.2f, White, LM.Roof);
            k.Prism(LandmarkKit.Rect(-178f, 25f, 23.5f, 191.5f), 17f, 18.2f, White, LM.Solid, 1.2f, White, LM.Roof);
            k.Prism(LandmarkKit.Rect(-178f, 25f, 16f, 182f), 18.2f, 18.6f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
            for (int i = 0; i < 3; i++)
            {
                float z = -45f + i * 60f, hi = 14.5f - (i == 1 ? 0f : 2f);
                W(k, Wbs.Apron, 0f, 0.4f);
                k.Prism(LandmarkKit.Rect(-140f, z, 60f, 28f), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);
                W(k, Wbs.LWing[i], 0.3f, hi + 0.4f);
                k.Prism(LandmarkKit.Rect(-153f, z, 28f, 18f), 0.3f, hi, GlassTeal, LM.Fins, 3.6f, White, LM.Roof);
                k.Prism(LandmarkKit.Rect(-125f, z, 28f, 18f), 0.3f, hi - 4f, GlassTeal, LM.Fins, 3.6f, White, LM.Roof);
                k.Prism(LandmarkKit.Rect(-153f, z, 25f, 15f), hi, hi + 0.4f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
                k.Prism(LandmarkKit.Rect(-125f, z, 25f, 15f), hi - 4f, hi - 3.6f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
                k.Box(new Vector3(-111.3f, (hi - 4f) * 0.5f + 0.15f, z), new Vector3(0.6f, hi - 4.3f, 18.6f), 0, White, LM.Solid, 1f, White, LM.Roof);
                if (i < 2)
                {
                    float cz = z + 30f;                                                           // the court between two wings
                    W(k, Wbs.LCourts, 0f, 9f);
                    Walk(k, new Vector2(-166f, cz), new Vector2(-104f, cz), 3.5f);
                    for (int t = 0; t < 4; t++) { k.Tree(new Vector3(-158f + t * 14f, 0.4f, cz - 9f), 8f, Leaf2, t * 0.21f + i); k.Tree(new Vector3(-158f + t * 14f, 0.4f, cz + 9f), 8f, Leaf, t * 0.37f + i); }
                }
            }

            // ---- north teaching block: a curved glass block with white fins and a green roof, facing the lake
            k.Part = 4;
            var ac = new Vector2(-15f, -40f); const float A0 = 58f, A1 = 122f; const int NS = 16;
            for (int s = 0; s < NS; s++)
            {
                float a0 = A0 + (A1 - A0) * s / NS, a1 = A0 + (A1 - A0) * (s + 1) / NS;
                // sectors (захватки) from the west end: the arc is cast four segments at a time, the green roof goes on last
                var sec = Wbs.NSector[Mathf.Min(3, (NS - 1 - s) * 4 / NS)];
                W(k, Wbs.Apron, 0f, 0.4f);
                k.Prism(Sector(ac, 153f, 183f, a0, a1), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);
                W(k, sec, 0.3f, 19.2f);
                k.Prism(Sector(ac, 160f, 176f, a0, a1), 0.3f, 18f, CampusBlue, LM.Glass, 4.2f, Roof, -1);
                k.Prism(Sector(ac, 158.5f, 177.5f, a0, a1), 18f, 19.2f, White, LM.Solid, 1.2f, White, LM.Roof, true);
                for (int f = 1; f < 3; f++) k.Prism(Sector(ac, 159.6f, 176.4f, a0, a1), f * 6f - 0.2f, f * 6f + 0.35f, White, LM.Solid, 0.55f, White, -1);
                W(k, Wbs.NRoof, 19.2f, 19.6f);
                k.Prism(Sector(ac, 163f, 173f, a0, a1), 19.2f, 19.6f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
            }
            for (int s = 0; s <= NS * 2; s++)
            {
                float a = (A0 + (A1 - A0) * s / (NS * 2)) * Mathf.Deg2Rad; var dir = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
                var pi = ac + dir * 159.5f; var po = ac + dir * 176.5f;
                W(k, Wbs.NSector[Mathf.Min(3, (NS * 2 - s) * 4 / (NS * 2 + 1))], 0.3f, 18f);
                k.Beam(new Vector3(pi.x, 0.3f, pi.y), new Vector3(pi.x, 18f, pi.y), 0.35f, 0.35f, White, LM.Solid, 1f);
                k.Beam(new Vector3(po.x, 0.3f, po.y), new Vector3(po.x, 18f, po.y), 0.35f, 0.35f, White, LM.Solid, 1f);
            }

            // ---- athletics: an oval track round a pitch, a stand with a canopy
            k.Part = 5;
            float sx = 140f, sz = -122f;
            W(k, Wbs.Apron, 0f, 0.4f);
            k.Prism(LandmarkKit.RoundRect(sx, sz, 124f, 80f, 38f, 6), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);
            W(k, Wbs.STrack, 0.38f, 0.5f);
            k.Prism(LandmarkKit.RoundRect(sx, sz, 112f, 68f, 34f, 6), 0.38f, 0.5f, Track, LM.Solid, 1f, Track, LM.Roof);
            W(k, Wbs.SPitch, 0.5f, 0.56f);
            k.Prism(LandmarkKit.RoundRect(sx, sz, 86f, 42f, 21f, 6), 0.5f, 0.56f, CampusTurf, LM.Solid, 1f, CampusTurf, LM.Plant);
            W(k, Wbs.SStand, 0.38f, 4.6f);
            for (int i = 0; i < 5; i++) k.Prism(LandmarkKit.Rect(sx, sz + 36f + i * 1.6f, 64f, 1.6f), 0.38f, 1.0f + i * 0.9f, Concrete, LM.Solid, 0.9f, White, LM.Paving);
            W(k, Wbs.SCanopy, 0.38f, 9.1f);
            k.Prism(LandmarkKit.Rect(sx, sz + 39f, 68f, 10f), 8.6f, 9.1f, White, LM.Solid, 1f, White, LM.Roof, true);
            for (int i = 0; i < 5; i++) k.Beam(new Vector3(sx - 32f + i * 16f, 0.38f, sz + 44f), new Vector3(sx - 32f + i * 16f, 8.6f, sz + 44f), 0.5f, 0.5f, White, LM.Solid);

            // ---- paths linking the lake, the halls, the tower and the sports ground
            k.Part = 6; W(k, Wbs.PPaths, 0f, 0.5f);
            Walk(k, new Vector2(lc.x + lrx + 12f, lc.y + 4f), new Vector2(112f, 20f), 5f);
            Walk(k, new Vector2(85f, 9f), new Vector2(112f, sz + 47f), 5f);          // to the sports ground: branches off the path to the tower, west of its apron
            Walk(k, new Vector2(lc.x, lc.y + lrz + 12f), new Vector2(lc.x, 118f), 6f);
            Walk(k, new Vector2(lc.x - lrx - 12f, lc.y - 4f), new Vector2(-104f, -15f), 5f);
            Walk(k, new Vector2(lc.x + 40f, lc.y + lrz + 6f), new Vector2(92f, 88f), 4f);
            Walk(k, new Vector2(lc.x - 40f, lc.y + lrz + 6f), new Vector2(-104f, 86f), 4f);

            // ---- the park trees: a double alley along the edge walk and groves on the lawns, kept off the buildings, paths and the lake
            bool Busy(float x, float z) => Mathf.Abs(x) > 196f || Mathf.Abs(z) > 166f || Bld(x, z);
            bool Bld(float x, float z)
            {
                if (x > mx - 92f && x < mx + 92f && z > mz - 39f && z < pz + 14f) return true;                                  // main hall, terrace, plaza
                if (x > 100f && x < 196f && z > -22f && z < 62f) return true;                                                     // tower apron
                if (x > -200f && x < -102f && z > -82f && z < 132f) return true;                                                   // laboratories
                if (x > 72f && x < 203f && z > -168f && z < -74f) return true;                                                     // sports
                if (x > -112f && x < -68f && z > tz - 9f && z < tz + 9f) return true;                                              // ramp
                float r = Vector2.Distance(new Vector2(x, z), ac), an = Mathf.Atan2(z - ac.y, x - ac.x) * Mathf.Rad2Deg;
                if (r > 146f && r < 190f && an > A0 - 4f && an < A1 + 4f) return true;                                             // north block
                float ex = (x - lc.x) / (lrx + 18f), ez = (z - lc.y) / (lrz + 18f); if (ex * ex + ez * ez < 1f) return true;     // lake, ring path
                return false;
            }
            float DistSeg(Vector2 p, Vector2 a, Vector2 b) { var ab = b - a; float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude); return Vector2.Distance(p, a + ab * t); }
            Vector2[] paths =
            {
                new Vector2(lc.x + lrx + 12f, lc.y + 4f), new Vector2(112f, 20f),
                new Vector2(85f, 9f), new Vector2(112f, sz + 47f), new Vector2(lc.x, lc.y + lrz + 12f), new Vector2(lc.x, 118f),
                new Vector2(lc.x - lrx - 12f, lc.y - 4f), new Vector2(-104f, -15f), new Vector2(lc.x + 40f, lc.y + lrz + 6f), new Vector2(92f, 88f),
                new Vector2(lc.x - 40f, lc.y + lrz + 6f), new Vector2(-104f, 86f)
            };
            bool OnPath(float x, float z, float m) { var p = new Vector2(x, z); for (int i = 0; i < paths.Length; i += 2) if (DistSeg(p, paths[i], paths[i + 1]) < m) return true; return false; }
            // the alley: two rows along the edge walk (the park's last stage: planting)
            W(k, Wbs.PTrees, 0.3f, 14f);
            foreach (float off in new[] { 192f, 205f })
            {
                float hw = off, hd = off - 30f;
                for (float x = -hw + 14f; x <= hw - 14f; x += 12f) foreach (float z in new[] { -hd, hd }) { if (!OnPath(x, z, 4f) && !Bld(x, z)) ParkTree(k, x, z, 10f + 2f * Hash(x, z), Hash(z, x)); }
                for (float z = -hd + 12f; z <= hd - 12f; z += 12f) foreach (float x in new[] { -hw, hw }) { if (!OnPath(x, z, 4f) && !Bld(x, z)) ParkTree(k, x, z, 10f + 2f * Hash(x, z), Hash(z, x)); }
            }
            // groves: jittered grid, denser near the lake
            for (float x = -184f; x <= 184f; x += 11f) for (float z = -156f; z <= 156f; z += 11f)
            {
                float h = Hash(x * 0.37f, z * 0.71f), jx = (Hash(x, z + 3f) - 0.5f) * 7f, jz = (Hash(x + 5f, z) - 0.5f) * 7f;
                float px = x + jx, qz = z + jz;
                float ex = (px - lc.x) / (lrx + 60f), ez = (qz - lc.y) / (lrz + 60f); float near = ex * ex + ez * ez < 1f ? 0.45f : 0.62f;
                if (h < near || Busy(px, qz) || OnPath(px, qz, 5f)) continue;
                if (Mathf.Abs(px) > 178f || Mathf.Abs(qz) > 148f) continue;                                                      // the alley is there
                ParkTree(k, px, qz, 8f + 5f * Hash(qz, px), h);
            }
            k.Part = 0; k.NoWin();
        }

        // ------------------------------------------------------------------ medical cluster: clinical podium, three ward towers, helipad
        static void Hospital(LandmarkKit k)
        {
            Pad(k, 280f, 210f, 14f, Pave);
            k.Prism(LandmarkKit.RoundRect(0, 0, 190f, 110f, 10f, 3), 0.3f, 14f, White, LM.Solid, 4.6f, Roof, LM.Roof);
            k.Prism(LandmarkKit.RoundRect(0, -53f, 170f, 6f, 2f, 2), 2f, 12f, GlassBlue, LM.Glass, 4.6f, Roof, -1);
            for (int i = 0; i < 3; i++)
            {
                float x = -60f + i * 60f;
                k.Prism(LandmarkKit.RoundRect(x, 10f, 44f, 22f, 6f, 3), 14f, 46f, GlassBlue, LM.Glass, 3.6f, White, -1);
                k.Box(new Vector3(x, 30f, 10f - 11.4f), new Vector3(36f, 32f, 0.8f), 0, White, LM.Fins, 3.6f, White, LM.Roof);
                k.Box(new Vector3(x, 46.6f, 10f), new Vector3(46f, 1.4f, 24f), 0, White, LM.Solid, 1f, Roof, LM.Roof);
            }
            k.Cylinder(new Vector3(60f, 47.3f, 10f), 9f, 0.5f, 24, MetalG, LM.Metal, 1f, LM.C("#2f7d4e"), LM.Paving);
            k.Box(new Vector3(60f, 47.85f, 10f), new Vector3(1.2f, 0.1f, 7f), 0, White, LM.Light, 1f, White, LM.Light);
            k.Box(new Vector3(-90f, 9f, -62f), new Vector3(30f, 1f, 14f), 0, Red, LM.Solid, 1f, Red, LM.Roof);   // emergency canopy
            Cars(k, 30f, -95f, 22, 2, 41f);
            Trees(k, -130f, 75f, 130f, 75f, 13f, 8f, 13f);
        }

        // ------------------------------------------------------------------ K-Park: Korean-style park and pavilions (10 ha)
        static void KPark(LandmarkKit k)
        {
            k.Prism(LandmarkKit.RoundRect(0, 0, 360f, 280f, 60f, 6), -16f, 0.35f, PaveDark, LM.Solid, 3f, Grass, LM.Plant);
            k.Prism(LandmarkKit.RoundRect(-40f, 20f, 120f, 70f, 34f, 6), 0.35f, 0.45f, Stone, LM.Solid, 1f, Water, LM.Water);
            k.Prism(LandmarkKit.Rect(0, -100f, 300f, 10f), 0.35f, 0.5f, Stone, LM.Solid, 1f, Pave, LM.Paving);
            k.Prism(LandmarkKit.Rect(110f, 0, 10f, 200f), 0.35f, 0.5f, Stone, LM.Solid, 1f, Pave, LM.Paving);
            // pavilions with wide, slightly lifted roofs (hanok-inspired)
            float[,] pv = { { -40f, 20f, 26f, 16f }, { 60f, 70f, 40f, 22f }, { 60f, -40f, 50f, 26f }, { -130f, -60f, 30f, 18f } };
            for (int i = 0; i < 4; i++)
            {
                float x = pv[i, 0], z = pv[i, 1], w = pv[i, 2], d = pv[i, 3];
                if (i == 0) z += 0f;
                k.Prism(LandmarkKit.Rect(x, z, w, d), 0.45f, 1.4f, Stone, LM.Solid, 1f, LM.C("#b9a88c"), LM.Paving);
                for (int c = 0; c < 4; c++) { float cx = x + (c % 2 == 0 ? -1 : 1) * (w * 0.5f - 1.5f), cz = z + (c < 2 ? -1 : 1) * (d * 0.5f - 1.5f); k.Beam(new Vector3(cx, 1.4f, cz), new Vector3(cx, 6.5f, cz), 0.6f, 0.6f, LM.C("#7a3f2a"), LM.Solid); }
                k.Prism(LandmarkKit.Rect(x, z, w - 3f, d - 3f), 1.4f, 6.2f, LM.C("#efe7d6"), LM.Solid, 1f, LM.C("#efe7d6"), -1);
                var eave = LandmarkKit.Rect(x, z, w + 8f, d + 8f); var ridge = LandmarkKit.Rect(x, z, w * 0.75f, 1.2f);
                k.Prism(eave, 6.5f, 7.1f, LM.C("#3b3d40"), LM.Solid, 1f, LM.C("#3b3d40"), -1);
                k.Loft(eave, 7.1f, ridge, 7.1f + d * 0.38f, LM.C("#33363a"), LM.Metal, 1f); k.Cap(ridge, 7.1f + d * 0.38f, true, LM.C("#2c2f33"), LM.Roof);
            }
            Trees(k, -165f, -125f, 165f, -115f, 15f, 9f, 21f); Trees(k, -165f, 115f, 165f, 125f, 15f, 9f, 22f);
            Trees(k, 140f, -90f, 160f, 90f, 16f, 9f, 23f);
            k.Beam(new Vector3(-150f, 0.4f, -120f), new Vector3(-150f, 9f, -120f), 1f, 1f, LM.C("#7a3f2a"), LM.Solid);
            k.Beam(new Vector3(-150f, 0.4f, -95f), new Vector3(-150f, 9f, -95f), 1f, 1f, LM.C("#7a3f2a"), LM.Solid);
            k.Beam(new Vector3(-150f, 9f, -124f), new Vector3(-150f, 9f, -91f), 1.4f, 1.2f, LM.C("#2c2f33"), LM.Solid);
        }

        // ------------------------------------------------------------------ marina and waterfront club on Kapshagay (Green District concept)
        static void Marina(LandmarkKit k)
        {
            Pad(k, 200f, 140f, 20f, Pave);
            k.Prism(LandmarkKit.RoundRect(-20f, 0, 90f, 34f, 14f, 5), 0.3f, 9.5f, GlassTeal, LM.Glass, 4.6f, White, -1);
            var r0 = LandmarkKit.RoundRect(-20f, 0, 104f, 46f, 20f, 5); var r1 = LandmarkKit.RoundRect(-20f, 0, 86f, 30f, 12f, 5);
            k.Loft(r0, 9.5f, r1, 12f, White, LM.Solid, 1f); k.Cap(r1, 12f, true, White, LM.Roof);
            k.Prism(LandmarkKit.Rect(80f, 0, 40f, 120f), 0.3f, 0.6f, Stone, LM.Solid, 1f, Pave, LM.Paving);        // quay
            // piers out over the water (+x) with moored yachts
            for (int p = 0; p < 4; p++)
            {
                float z = -54f + p * 36f;
                k.Prism(LandmarkKit.Rect(200f, z, 240f, 3.2f), -0.6f, 0.9f, LM.C("#8a7a64"), LM.Solid, 1f, LM.C("#a8977c"), LM.Paving);
                for (int b = 0; b < 9; b++)
                {
                    if ((b + p) % 3 == 1) continue;
                    float x = 110f + b * 25f, side = (b % 2 == 0) ? 7f : -7f; float L = 14f + (b * 3 + p) % 4 * 3f;
                    var hull0 = LandmarkKit.Chamfer(x, z + side, L, 4.2f, 1.6f); var hull1 = LandmarkKit.Chamfer(x + 0.6f, z + side, L - 3f, 2.8f, 1.0f);
                    k.Loft(hull1, -0.3f, hull0, 1.4f, White, LM.Solid, 1f); k.Cap(hull0, 1.4f, true, LM.C("#cdbb98"), LM.Paving);
                    k.Box(new Vector3(x - 1f, 2.4f, z + side), new Vector3(L * 0.45f, 2f, 3f), 0, White, LM.Glass, 1f, White, LM.Roof);
                    if (b % 3 == 0) k.Beam(new Vector3(x, 1.4f, z + side), new Vector3(x, 1.4f + L * 1.3f, z + side), 0.25f, 0.25f, MetalG, LM.Steel);
                }
            }
            Trees(k, -95f, -60f, 60f, -60f, 12f, 8f, 31f); Trees(k, -95f, 60f, 60f, 60f, 12f, 8f, 32f);
            for (int i = 0; i < 8; i++) k.Box(new Vector3(-80f + i * 20f, 3.2f, -36f), new Vector3(0.3f, 6f, 0.3f), 0, Steel, LM.Steel, 1f, Warm, LM.Light);
        }
    }
}
