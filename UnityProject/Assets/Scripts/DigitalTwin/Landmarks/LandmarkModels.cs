using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Procedural models of the landmarks. Local frame: x = long side, z = across, y = up from the base (0 = ground).
    /// Proportions follow the published figures (heights, areas, capacities); details are illustrative, not design documentation.</summary>
    public static class LandmarkModels
    {
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

        // ------------------------------------------------------------------ Iconic Complex (SOM): a 272 m wedge tower + an 80 m terraced hotel tower on a terraced podium
        static void Iconic(LandmarkKit k)
        {
            Pad(k, 270f, 200f, 22f, Pave);
            // podium: three glazed levels with white fascias, stepping back and down toward the public square (south, −z), planted terraces
            float[,] lv = { { 0.3f, 8.5f, 196f, 126f, 6f, 12f }, { 8.5f, 15f, 164f, 102f, 16f, 22f }, { 15f, 21f, 128f, 82f, 26f, 30f } };
            for (int i = 0; i < 3; i++)
            {
                float y0 = lv[i, 0], y1 = lv[i, 1], w = lv[i, 2], d = lv[i, 3], cx = lv[i, 4], cz = lv[i, 5];
                k.Prism(LandmarkKit.RoundRect(cx, cz, w, d, 16f, 5), y0, y1 - 1.6f, GlassWarm, LM.Glass, 4.3f, White, -1);
                k.Prism(LandmarkKit.RoundRect(cx, cz, w + 2.4f, d + 2.4f, 17f, 5), y1 - 1.6f, y1, White, LM.Solid, 1.6f, Stone, LM.Paving);
                // light line under each fascia (warm white at night)
                k.Prism(LandmarkKit.RoundRect(cx, cz, w + 2.5f, d + 2.5f, 17f, 5), y1 - 1.75f, y1 - 1.6f, Warm, LM.Light, 1f, Warm, -1);
                if (i < 2)
                {
                    // planted strip on the exposed terrace in front of the next level
                    float nz = lv[i + 1, 5] - lv[i + 1, 3] * 0.5f, z0 = cz - d * 0.5f + 3f;
                    k.Prism(LandmarkKit.RoundRect(cx, (z0 + nz) * 0.5f - 1f, w - 14f, Mathf.Max(3f, nz - z0 - 4f), 3f, 2), y1, y1 + 0.6f, Stone, LM.Solid, 3f, Grass, LM.Plant);
                }
            }
            // atrium roof light over the podium
            k.Prism(LandmarkKit.RoundRect(-6f, 34f, 40f, 30f, 12f, 4), 21f, 22.2f, GlassBlue, LM.Glass, 1.2f, GlassBlue, LM.Glass);

            // ---- main tower: one vertical face (east, +x) with a white spine, the other leans in to a blade-shaped crown
            float xr = 66f, cz0 = 34f, W0 = 60f, D0 = 44f, H = 272f, roof = 252f, fh = 4.3f;
            List<Vector2> Ring(float y)
            {
                float f = Mathf.Clamp01(y / roof);
                float w = W0 * (1f - 0.74f * Mathf.Pow(f, 1.25f)), d = D0 * (1f - 0.28f * f);
                return LandmarkKit.Chamfer(xr - w * 0.5f, cz0, Mathf.Max(w, 5f), d, Mathf.Min(5f, w * 0.18f));
            }
            var prev = Ring(0.3f); float yp = 0.3f;
            for (float y = 0.3f + fh; y <= roof + 0.01f; y += fh)
            {
                var r = Ring(y); k.Loft(prev, yp, r, y, GlassBlue, LM.Fins, fh); prev = r; yp = y;
            }
            // crown: the lean continues as a glass blade to a sharp ridge, then the mast
            float wTop = W0 * (1f - 0.74f), dTop = D0 * 0.72f;
            var ridge = LandmarkKit.Chamfer(xr - 1.2f, cz0, 2.4f, dTop * 0.55f, 0.5f);
            k.Loft(prev, yp, ridge, 264f, GlassBlue, LM.Glass, 2.2f);
            k.Cap(ridge, 264f, true, MetalG, LM.Metal);
            k.Beam(new Vector3(xr - 1.2f, 263f, cz0), new Vector3(xr - 1.2f, H, cz0), 0.9f, 0.9f, MetalG, LM.Steel);
            k.Box(new Vector3(xr - 1.2f, H - 0.4f, cz0), new Vector3(1.4f, 0.8f, 1.4f), 0, Red, LM.Light, 1f, Red, LM.Light);
            // crown light band and the white spine on the vertical face
            k.Box(new Vector3(xr - wTop * 0.5f, roof - 0.6f, cz0), new Vector3(wTop + 1.2f, 1.2f, dTop + 1.2f), 0, Warm, LM.Light, 1f, Warm, -1);
            k.Box(new Vector3(xr + 1.0f, 131f, cz0), new Vector3(2.2f, 262f, 7f), 0, White, LM.Solid, fh, White, LM.Roof);
            // tower lobby canopy toward the square
            k.Box(new Vector3(xr - 30f, 9.3f, cz0 - D0 * 0.5f - 8f), new Vector3(26f, 0.8f, 16f), 0, White, LM.Solid, 1f, White, LM.Roof);

            // ---- hotel and branded residences: 80 m, terraces stepping down to the west like the foothills
            float hx = -46f, hz = 36f, hw = 66f, hd = 34f, step = 10.8f;
            for (int s = 0; s < 8; s++)
            {
                float y0 = s == 0 ? 0.3f : s * step, y1 = Mathf.Min((s + 1) * step, 80f);
                float w = hw - s * 6.6f; float cx = hx + (hw - w) * 0.5f;
                k.Prism(LandmarkKit.RoundRect(cx, hz, w, hd, 5f, 3), y0, y1 - 1.1f, GlassTeal, LM.Glass, 3.6f, White, -1);
                k.Prism(LandmarkKit.RoundRect(cx, hz, w + 1.6f, hd + 1.6f, 5.5f, 3), y1 - 1.1f, y1, White, LM.Solid, 1.1f, Stone, LM.Paving);
                // planted terrace on the step that is not covered by the next floor
                if (s < 7) k.Prism(LandmarkKit.Rect(cx - w * 0.5f + 3.6f, hz, 5.4f, hd - 4f), y1, y1 + 0.7f, Stone, LM.Solid, 1f, Grass, LM.Plant);
            }
            k.Box(new Vector3(hx + (hw - 20f) * 0.5f, 81.6f, hz), new Vector3(16f, 3.2f, 20f), 0, MetalG, LM.Metal, 3f, Roof, LM.Roof);

            // ---- the square: reflecting pool, lawns, trees, paths
            k.Prism(LandmarkKit.RoundRect(-36f, -64f, 92f, 20f, 9f, 3), 0.3f, 0.5f, Stone, LM.Solid, 1f, Water, LM.Water);
            Lawn(k, 64f, -66f, 70f, 34f, 8f); Lawn(k, -112f, -10f, 26f, 120f, 8f); Lawn(k, 118f, 24f, 22f, 110f, 8f);
            Trees(k, 36f, -78f, 92f, -56f, 14f, 9f, 1f);
            Trees(k, -118f, -60f, -108f, 50f, 13f, 9f, 2f);
            Trees(k, 112f, -24f, 124f, 70f, 13f, 9f, 3f);
            for (int i = 0; i < 9; i++) k.Box(new Vector3(-80f + i * 11f, 3.2f, -58f), new Vector3(0.35f, 6f, 0.35f), 0, Steel, LM.Steel, 1f, Warm, LM.Light);
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

        // ------------------------------------------------------------------ university campus (KAIST Kazakhstan): quad, main hall, library tower, labs
        static void Campus(LandmarkKit k)
        {
            Pad(k, 420f, 360f, 30f, Pave);
            Lawn(k, 0, 0, 180f, 120f, 30f);
            Trees(k, -84f, -56f, 84f, -56f, 14f, 9f, 11f); Trees(k, -84f, 56f, 84f, 56f, 14f, 9f, 12f);
            // main hall with a sweeping glass roof
            k.Prism(LandmarkKit.RoundRect(0, -120f, 160f, 56f, 20f, 5), 0.3f, 22f, GlassBlue, LM.Glass, 4.4f, White, -1);
            var r0 = LandmarkKit.RoundRect(0, -120f, 166f, 62f, 22f, 5); var r1 = LandmarkKit.RoundRect(0, -120f, 120f, 34f, 14f, 5);
            k.Loft(r0, 22f, r1, 30f, White, LM.Solid, 2f); k.Cap(r1, 30f, true, White, LM.Roof);
            // library tower
            k.Prism(LandmarkKit.Chamfer(150f, 20f, 40f, 40f, 6f), 0.3f, 58f, GlassTeal, LM.Fins, 3.8f, Roof, LM.Roof);
            // labs and faculties around the quad
            for (int i = 0; i < 3; i++) k.Prism(LandmarkKit.Rect(-140f + i * 0f, -40f + i * 60f, 70f, 34f), 0.3f, 18f + i * 3f, White, LM.Solid, 3.8f, Roof, LM.Roof);
            for (int i = 0; i < 3; i++) k.Box(new Vector3(-140f, 9f + i * 1.5f, -40f + i * 60f), new Vector3(72f, 7f, 36f), 0, GlassWarm, LM.Glass, 3.8f, Roof, LM.Roof);
            k.Prism(LandmarkKit.Rect(40f, 120f, 150f, 40f), 0.3f, 16f, White, LM.Solid, 3.8f, Roof, LM.Roof);
            k.Prism(LandmarkKit.Rect(40f, 120f, 146f, 36f), 3f, 13f, GlassBlue, LM.Glass, 3.8f, Roof, -1);
            // sports field
            k.Prism(LandmarkKit.Rect(150f, -120f, 90f, 60f), 0.3f, 0.5f, LM.C("#8a3b2c"), LM.Solid, 1f, LM.C("#4f8a43"), LM.Plant);
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
