using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Car parks with marked bays and the redrawn models of the medical cluster, K-Park, L7 and the logistics park
    /// (massing with setbacks, entrances and canopies, roof plant, landscaping). Built from the LandmarkKit primitives only.</summary>
    public static partial class LandmarkModels
    {
        static readonly Color32 LotAsph = LM.C("#5a5b5c"), LotLine = LM.C("#ecebe4"), Kerb = LM.C("#b8b3a8"), Ambulance = LM.C("#f4f4f2");
        static readonly Color32[] CarCols = { LM.C("#e9e9e7"), LM.C("#26282b"), LM.C("#80868e"), LM.C("#9a2a24"), LM.C("#2d4b74"), LM.C("#c8c9c9"), LM.C("#3d3f42"), LM.C("#d9d4c8") };

        /// <summary>One parked car: body, glazed cabin, axis along local z when yaw = 0.</summary>
        static void Car(LandmarkKit k, float x, float z, float y, float yaw, Color32 col)
        {
            var r = Quaternion.Euler(0f, yaw, 0f);
            k.Box(new Vector3(x, y + 0.42f, z), new Vector3(1.82f, 0.74f, 4.4f), yaw, col, LM.Solid, 1f, col, LM.Metal);
            var c = new Vector3(x, y + 1.05f, z) + r * new Vector3(0f, 0f, -0.25f);
            k.Box(c, new Vector3(1.56f, 0.56f, 2.3f), yaw, GlassDark, LM.Glass, 1f, col, LM.Metal);
        }

        /// <summary>Surface car park on the plot's grid: asphalt with a kerb, double rows of 2.6 × 5 m bays (painted lines) along local x,
        /// 6.5 m aisles, planted islands at the row ends; 'fill' of the bays taken. Cars stand nose-in, square to the bays.</summary>
        static void Lot(LandmarkKit k, float x0, float x1, float z0, float z1, float fill, float seed)
        {
            float w = x1 - x0, d = z1 - z0; if (w < 20f || d < 12f) return;
            k.Prism(LandmarkKit.Rect((x0 + x1) * 0.5f, (z0 + z1) * 0.5f, w + 1.2f, d + 1.2f), 0.25f, 0.5f, Kerb, LM.Solid, 1f, Kerb, LM.Paving);
            k.Prism(LandmarkKit.Rect((x0 + x1) * 0.5f, (z0 + z1) * 0.5f, w, d), 0.25f, 0.52f, LotAsph, LM.Solid, 1f, LotAsph, LM.Paving);
            const float bay = 2.6f, depth = 5f, aisle = 6.5f, module = depth * 2f + aisle;
            float ux0 = x0 + 7f, ux1 = x1 - 7f; int nb = Mathf.FloorToInt((ux1 - ux0) / bay); if (nb < 2) return;
            float bx0 = (x0 + x1) * 0.5f - nb * bay * 0.5f;
            int rowsN = Mathf.Max(1, Mathf.FloorToInt((d - aisle) / module));
            float zs = (z0 + z1) * 0.5f - (rowsN * module - aisle) * 0.5f;
            for (int m = 0; m < rowsN; m++)
            {
                float zr = zs + m * module;
                for (int side = 0; side < 2; side++)
                {
                    float zc = zr + depth * 0.5f + side * depth;      // two rows back to back, the shared line at zr + depth
                    for (int i = 0; i <= nb; i++)
                        k.Box(new Vector3(bx0 + i * bay, 0.54f, zc), new Vector3(0.12f, 0.03f, depth - 0.4f), 0f, LotLine, LM.Solid, 1f, LotLine, LM.Light);
                    for (int i = 0; i < nb; i++)
                    {
                        float h = Mathf.Abs(Mathf.Sin((i * 12.9898f + (m * 2 + side) * 78.233f + seed) * 0.731f));
                        if (h > fill) continue;
                        Car(k, bx0 + (i + 0.5f) * bay, zc + (side == 0 ? 0.25f : -0.25f), 0.52f, 0f, CarCols[(int)(h * 997f) % CarCols.Length]);
                    }
                }
                k.Box(new Vector3((x0 + x1) * 0.5f, 0.54f, zr + depth), new Vector3(nb * bay, 0.03f, 0.12f), 0f, LotLine, LM.Solid, 1f, LotLine, LM.Light);
                // planted islands with a tree at both ends of the double row
                foreach (float xe in new[] { bx0 - 3.2f, bx0 + nb * bay + 3.2f })
                {
                    k.Prism(LandmarkKit.Rect(xe, zr + depth, 4.4f, depth * 2f - 0.6f), 0.5f, 0.7f, Kerb, LM.Solid, 1f, GrassDark, LM.Plant);
                    k.Tree(new Vector3(xe, 0.7f, zr + depth), 7f, Leaf, xe + zr);
                }
            }
        }

        /// <summary>Rooftop plant: air handling units, a lift overrun and a screen, kept inside the roof outline (cx, cz, w × d at height y).</summary>
        static void RoofPlant(LandmarkKit k, float cx, float cz, float w, float d, float y, float seed)
        {
            k.Box(new Vector3(cx - w * 0.22f, y + 1.7f, cz), new Vector3(Mathf.Min(8f, w * 0.18f), 3.4f, Mathf.Min(6f, d * 0.3f)), 0f, Concrete, LM.Solid, 3.4f, Roof, LM.Roof);
            int n = Mathf.Clamp(Mathf.FloorToInt(w / 14f), 1, 4);
            for (int i = 0; i < n; i++)
            {
                float x = cx + w * 0.05f + i * 7.5f - (n - 1) * 3.75f + w * 0.12f;
                k.Box(new Vector3(x, y + 1.1f, cz + d * 0.12f), new Vector3(5.5f, 2.2f, Mathf.Min(3.4f, d * 0.25f)), 0f, MetalG, LM.Metal, 2.2f, MetalD, LM.Metal);
                k.Cylinder(new Vector3(x - 1.5f, y + 2.2f, cz + d * 0.12f), 0.7f, 0.5f, 10, MetalD, LM.Metal, 1f, Steel, LM.Steel);
                k.Cylinder(new Vector3(x + 1.5f, y + 2.2f, cz + d * 0.12f), 0.7f, 0.5f, 10, MetalD, LM.Metal, 1f, Steel, LM.Steel);
            }
            // parapet round the roof
            var r = LandmarkKit.Rect(cx, cz, w, d);
            for (int i = 0; i < 4; i++) { var a = r[i]; var b = r[(i + 1) % 4]; k.Beam(new Vector3(a.x, y, a.y), new Vector3(b.x, y, b.y), 0.35f, 1.1f, White, LM.Solid); }
        }

        // ------------------------------------------------------------------ medical cluster (plot 280 × 210, front = −z, the street):
        // a two-level clinical podium (glazed ground floor, white upper floor with ribbon windows) stepped back behind a landscaped forecourt,
        // a glass entrance hall with a deep canopy over the drop-off loop, three ward towers with a recessed top floor and roof plant, a helipad
        // on a frame over the east tower, the emergency entrance with ambulance bays on the west side, staff and visitor car parks with bays.
        static void Hospital(LandmarkKit k)
        {
            // the plot is a planted campus: lawn over the whole plot, paving only round the building, the forecourt and the emergency apron
            Pad(k, 280f, 210f, 14f, Grass, LM.Plant);
            k.Prism(LandmarkKit.RoundRect(0f, 10f, 212f, 124f, 12f, 3), 0.3f, 0.42f, PaveDark, LM.Solid, 1f, Pave, LM.Paving);
            k.Prism(LandmarkKit.RoundRect(0f, -76f, 104f, 48f, 8f, 3), 0.3f, 0.42f, PaveDark, LM.Solid, 1f, Pave, LM.Paving);
            k.Prism(LandmarkKit.Rect(-108f, 12f, 30f, 48f), 0.3f, 0.43f, PaveDark, LM.Solid, 1f, LM.C("#8d8a84"), LM.Paving);
            k.Prism(LandmarkKit.Rect(87f, -60f, 6f, 30f), 0.3f, 0.42f, PaveDark, LM.Solid, 1f, Pave, LM.Paving);
            // podium: glazed ground floor, white upper floor, a step back on the front
            k.Prism(LandmarkKit.RoundRect(0f, 12f, 190f, 96f, 8f, 3), 0.3f, 5.2f, GlassBlue, LM.Glass, 5f, White, -1);
            k.Prism(LandmarkKit.RoundRect(0f, 12f, 194f, 100f, 9f, 3), 5.2f, 6.0f, White, LM.Solid, 1f, White, -1);
            k.Prism(LandmarkKit.RoundRect(0f, 16f, 186f, 88f, 8f, 3), 6.0f, 14.5f, White, LM.Solid, 4.2f, Roof, LM.Roof);
            k.Prism(LandmarkKit.RoundRect(0f, 16f, 188f, 90f, 8f, 3), 14.5f, 15.3f, White, LM.Solid, 1f, White, -1);
            // green roof on the podium between the towers, a courtyard light well
            k.Prism(LandmarkKit.RoundRect(-30f, 40f, 40f, 24f, 4f, 2), 14.5f, 15.0f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
            k.Prism(LandmarkKit.RoundRect(30f, 40f, 40f, 24f, 4f, 2), 14.5f, 15.0f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
            // entrance hall: a glass box under a deep white canopy on slim columns
            k.Prism(LandmarkKit.RoundRect(0f, -42f, 46f, 16f, 3f, 2), 0.3f, 11f, GlassTeal, LM.Glass, 5.5f, White, LM.Roof);
            k.Box(new Vector3(0f, 7.2f, -58f), new Vector3(56f, 0.9f, 22f), 0f, White, LM.Solid, 1f, White, LM.Roof);
            for (int i = 0; i < 4; i++) { float x = -24f + i * 16f; k.Beam(new Vector3(x, 0.3f, -67f), new Vector3(x, 6.8f, -67f), 0.5f, 0.5f, MetalW, LM.Steel); }
            k.Box(new Vector3(0f, 8.3f, -68.8f), new Vector3(30f, 1.3f, 0.4f), 0f, LM.C("#1f7a4c"), LM.Light, 1f, LM.C("#1f7a4c"), LM.Light);   // green sign band
            // drop-off loop in front of the canopy
            var loop = LandmarkKit.RoundRect(0f, -70f, 78f, 26f, 12f, 4);
            Road(k, loop, 3.6f, true, false);
            Lawn(k, 0f, -70f, 56f, 6f, 2.5f);
            // ward towers: 8 floors over the podium, vertical fins, a recessed glass top floor, roof plant
            for (int i = 0; i < 3; i++)
            {
                float x = -60f + i * 60f, z = 18f;
                k.Prism(LandmarkKit.RoundRect(x, z, 44f, 22f, 6f, 3), 15.3f, 42f, GlassBlue, LM.Glass, 3.6f, White, -1);
                k.Box(new Vector3(x, 28.6f, z - 11.4f), new Vector3(36f, 26.6f, 0.8f), 0, White, LM.Fins, 3.6f, White, LM.Roof);
                k.Box(new Vector3(x, 28.6f, z + 11.4f), new Vector3(36f, 26.6f, 0.8f), 0, White, LM.Fins, 3.6f, White, LM.Roof);
                k.Prism(LandmarkKit.RoundRect(x, z, 46f, 24f, 6f, 3), 42f, 42.8f, White, LM.Solid, 1f, White, -1);
                k.Prism(LandmarkKit.RoundRect(x, z, 38f, 18f, 4f, 3), 42.8f, 46.2f, GlassDark, LM.Glass, 3.4f, Roof, LM.Roof);
                if (i != 2) RoofPlant(k, x, z, 34f, 16f, 46.2f, i);
            }
            // helipad on a steel frame over the east tower
            for (int c = 0; c < 4; c++) { float cx = 60f + (c % 2 == 0 ? -8f : 8f), cz = 18f + (c < 2 ? -6f : 6f); k.Beam(new Vector3(cx, 46.2f, cz), new Vector3(cx, 48f, cz), 0.5f, 0.5f, Steel, LM.Steel); }
            k.Cylinder(new Vector3(60f, 48f, 18f), 11f, 0.5f, 28, MetalG, LM.Metal, 1f, LM.C("#2f7d4e"), LM.Paving);
            k.Box(new Vector3(57.5f, 48.55f, 18f), new Vector3(0.9f, 0.05f, 7f), 0, White, LM.Light, 1f, White, LM.Light);
            k.Box(new Vector3(62.5f, 48.55f, 18f), new Vector3(0.9f, 0.05f, 7f), 0, White, LM.Light, 1f, White, LM.Light);
            k.Box(new Vector3(60f, 48.55f, 18f), new Vector3(5f, 0.05f, 0.9f), 0, White, LM.Light, 1f, White, LM.Light);
            // emergency entrance on the west end: red canopy, ambulance bays, ambulances
            k.Box(new Vector3(-104f, 5.4f, 10f), new Vector3(14f, 0.8f, 30f), 0, Red, LM.Solid, 1f, Red, LM.Roof);
            for (int i = 0; i < 2; i++) k.Beam(new Vector3(-110f, 0.3f, -2f + i * 24f), new Vector3(-110f, 5f, -2f + i * 24f), 0.45f, 0.45f, MetalW, LM.Steel);
            for (int i = 0; i < 3; i++)
            {
                float z = 0f + i * 9f;
                k.Box(new Vector3(-104f, 1.6f, z), new Vector3(5.6f, 2.6f, 2.3f), 0, Ambulance, LM.Solid, 1f, Ambulance, LM.Roof);
                k.Box(new Vector3(-104f, 1.4f, z), new Vector3(5.62f, 0.35f, 2.32f), 0, Red, LM.Solid, 1f, Red, LM.Solid);
            }
            // driveways to the street that runs along the front of the plot (≈ 15–25 m beyond its edge, slightly skewed): from the drop-off
            // loop, the visitor car park and the west service lane (emergency apron and the staff car park at the back); laid down to −6 m
            // so they meet the terrain outside the levelled plot
            k.Prism(LandmarkKit.Rect(0f, -103.5f, 12f, 37f), -6f, 0.47f, PaveDark, LM.Solid, 1f, LotAsph, LM.Paving);
            k.Prism(LandmarkKit.Rect(87f, -109f, 10f, 14f), -6f, 0.53f, PaveDark, LM.Solid, 1f, LotAsph, LM.Paving);
            k.Prism(LandmarkKit.Rect(-122f, -27.5f, 10f, 199f), -6f, 0.45f, PaveDark, LM.Solid, 1f, LotAsph, LM.Paving);
            RoofPlant(k, -62f, -14f, 34f, 18f, 14.5f, 7f); RoofPlant(k, 62f, -14f, 34f, 18f, 14.5f, 8f);
            for (int i = 0; i < 6; i++) k.Box(new Vector3(-75f + i * 30f, 15.1f, 50f), new Vector3(8f, 1.2f, 8f), 0f, GlassBlue, LM.Glass, 1f, LM.C("#aab4bd"), LM.Glass);
            // car parks: visitors on the front east, staff on the back west; trees along the street edge
            Lot(k, 54f, 134f, -102f, -64f, 0.72f, 41f);
            Lot(k, -134f, -60f, 70f, 102f, 0.8f, 43f);
            Trees(k, -110f, -101f, -40f, -101f, 11f, 8f, 13f);
            Trees(k, 26f, 100f, 132f, 100f, 12f, 8f, 14f);
        }

        // ------------------------------------------------------------------ K-Park (10 ha, Korean garden): a ring walk round the park, a
        // paved axis from the south gate (a red-columned gate with a tiled roof) to a stone plaza, a lotus pond with an island pavilion and
        // an arched bridge, four hanok pavilions (white walls, red columns, grey tiled roofs with lifted eaves), groves of trees on the lawns,
        // flower beds, stone lanterns and lamps.
        static void KPark(LandmarkKit k)
        {
            var paveK = LM.C("#cdbfa6"); var col = LM.C("#8c2f22"); var wall = LM.C("#efe9dc"); var tile = LM.C("#4b5058"); var tileDark = LM.C("#3c4047");
            k.Planted = true;
            k.Prism(LandmarkKit.RoundRect(0, 0, 360f, 280f, 60f, 6), -16f, 0.35f, PaveDark, LM.Solid, 3f, LM.C("#76925a"), LM.Plant, false, LandmarkKit.GreenTag);
            // ring walk inside the edge and the axis from the south gate to the plaza
            var ringO = LandmarkKit.RoundRect(0, 0, 330f, 250f, 48f, 6); var ringI = LandmarkKit.RoundRect(0, 0, 322f, 242f, 44f, 6);
            Band(k, ringI, ringO, 0.35f, 0.5f, Stone, paveK, LM.Paving, LandmarkKit.GreenTag);
            k.Prism(LandmarkKit.Rect(60f, -78f, 8f, 94f), 0.35f, 0.5f, Stone, LM.Solid, 1f, paveK, LM.Paving);
            k.Prism(LandmarkKit.Circle(60f, -10f, 22f, 24), 0.35f, 0.52f, Stone, LM.Solid, 1f, paveK, LM.Paving);
            k.Prism(LandmarkKit.Rect(5f, -10f, 90f, 6f), 0.35f, 0.5f, Stone, LM.Solid, 1f, paveK, LM.Paving);
            k.Prism(LandmarkKit.Rect(60f, 50f, 6f, 100f), 0.35f, 0.5f, Stone, LM.Solid, 1f, paveK, LM.Paving);
            // lotus pond with a stone rim, an island and an arched bridge
            // an irregular shore (two lobes and a cove), a low stone edge with a reed margin
            List<Vector2> Shore(float grow)
            {
                var l = new List<Vector2>();
                for (int i = 0; i < 48; i++)
                {
                    float a = i * Mathf.PI * 2f / 48f;
                    float r = 1f + 0.13f * Mathf.Sin(2f * a + 0.6f) + 0.07f * Mathf.Sin(3f * a + 1.9f) - 0.05f * Mathf.Cos(5f * a);
                    l.Add(new Vector2(-70f + Mathf.Cos(a) * (60f * r + grow), 25f + Mathf.Sin(a) * (34f * r + grow)));
                }
                return l;
            }
            k.Prism(Shore(4f), 0.35f, 0.5f, GrassDark, LM.Solid, 1f, LM.C("#6f8a46"), LM.Plant);
            k.Prism(Shore(1.2f), 0.35f, 0.58f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            k.Prism(Shore(0f), 0.35f, 0.6f, Stone, LM.Solid, 1f, Water, LM.Water);
            k.Prism(LandmarkKit.Circle(-60f, 30f, 12f, 16), 0.35f, 1.0f, Stone, LM.Solid, 1f, Grass, LM.Plant);
            for (int i = 0; i < 9; i++)
            {
                float t0 = i / 9f, t1 = (i + 1) / 9f; float xa = Mathf.Lerp(-48f, -4f, t0), xb = Mathf.Lerp(-48f, -4f, t1);
                float ya = 1.0f + Mathf.Sin(t0 * Mathf.PI) * 2.2f, yb = 1.0f + Mathf.Sin(t1 * Mathf.PI) * 2.2f;
                k.Slab(new Vector3(xa, ya, 28f), new Vector3(xb, yb, 28f), new Vector3(xb, yb, 32f), new Vector3(xa, ya, 32f), 0.35f, col, LM.Solid);
            }
            for (int i = 0; i < 7; i++) { float x = -64f + i * 7f; k.Cylinder(new Vector3(x, 0.62f, 8f + (i % 3) * 3f), 1.6f, 0.08f, 8, LM.C("#3f6b3a"), LM.Plant, 1f, LM.C("#d98aa0"), LM.Plant); }
            // pavilions: island (small), east hall, north hall, west tea house
            Hanok(k, -60f, 30f, 12f, 10f, 1.0f, wall, col, tile, tileDark);
            Hanok(k, 60f, 62f, 40f, 18f, 0.5f, wall, col, tile, tileDark);
            Hanok(k, 60f, -10f, 22f, 14f, 0.52f, wall, col, tile, tileDark);
            Hanok(k, -130f, -60f, 26f, 14f, 0.5f, wall, col, tile, tileDark);
            // south gate on the axis
            for (int s = -1; s <= 1; s += 2) k.Beam(new Vector3(60f + s * 5f, 0.4f, -122f), new Vector3(60f + s * 5f, 7.5f, -122f), 0.8f, 0.8f, col, LM.Solid);
            k.Box(new Vector3(60f, 7.8f, -122f), new Vector3(16f, 0.6f, 4.4f), 0f, tileDark, LM.Solid, 1f, tile, LM.Roof);
            k.Loft(LandmarkKit.Rect(60f, -122f, 16f, 4.4f), 8.1f, LandmarkKit.Rect(60f, -122f, 11f, 0.6f), 10f, tile, LM.Metal, 1f);
            // flower beds along the axis, stone lanterns and lamps
            for (int i = 0; i < 4; i++)
            {
                float z = -112f + i * 22f;
                k.Prism(LandmarkKit.RoundRect(50f, z, 6f, 14f, 2f, 2), 0.35f, 0.7f, Stone, LM.Solid, 1f, i % 2 == 0 ? LM.C("#c94f6d") : LM.C("#e3b23c"), LM.Plant);
                k.Prism(LandmarkKit.RoundRect(70f, z, 6f, 14f, 2f, 2), 0.35f, 0.7f, Stone, LM.Solid, 1f, i % 2 == 0 ? LM.C("#e3b23c") : LM.C("#c94f6d"), LM.Plant);
                k.Box(new Vector3(45f, 1.1f, z + 9f), new Vector3(0.9f, 1.5f, 0.9f), 0f, Stone, LM.Solid, 1f, Warm, LM.Light);
                k.Box(new Vector3(75f, 1.1f, z + 9f), new Vector3(0.9f, 1.5f, 0.9f), 0f, Stone, LM.Solid, 1f, Warm, LM.Light);
            }
            // groves on the lawns, kept off the walks, the pond and the pavilions
            bool Free(float x, float z)
            {
                float u = x / 165f, v = z / 125f; if (u * u + v * v > 0.86f) return false;
                if (Mathf.Abs(x - 60f) < 17f && z < 110f) return false;                       // axis
                if (Mathf.Abs(z + 10f) < 9f && x > -45f && x < 85f) return false;            // cross walk
                if (Mathf.Abs(x + 70f) < 82f && Mathf.Abs(z - 25f) < 52f) return false;       // pond
                if (Mathf.Abs(x - 60f) < 30f && z > 40f && z < 85f) return false;            // north hall
                if (Mathf.Abs(x - 60f) < 26f && Mathf.Abs(z + 10f) < 26f) return false;       // plaza
                if (Mathf.Abs(x + 130f) < 20f && Mathf.Abs(z + 60f) < 14f) return false;      // tea house
                return true;
            }
            int n = 0;
            for (float x = -160f; x <= 160f; x += 9f)
                for (float z = -120f; z <= 120f; z += 9f)
                {
                    float h = Mathf.Abs(Mathf.Sin(x * 0.173f + z * 0.311f) * Mathf.Cos(x * 0.051f - z * 0.087f));
                    // groves: dense where a slow noise is high, open lawns elsewhere
                    if (h < 0.35f) continue;
                    float jx = x + Mathf.Sin(z * 1.7f + x) * 3f, jz = z + Mathf.Cos(x * 1.3f - z) * 3f;
                    if (!Free(jx, jz)) continue;
                    ParkTree(k, jx, jz, 7f + h * 6f, n++);
                }
            // a double row of trees along the ring walk
            for (int i = 0; i < 64; i++)
            {
                float a = i * Mathf.PI * 2f / 64f; float x = Mathf.Cos(a) * 148f, z = Mathf.Sin(a) * 110f;
                if (Mathf.Abs(x - 60f) < 10f && z < 0f) continue;
                k.Tree(new Vector3(x, 0.4f, z), 9f, (i & 1) == 0 ? Leaf : Leaf2, i);
            }
            k.Planted = false;
        }

        /// <summary>A hanok pavilion: stone plinth, red columns, white walls, a grey tiled hip roof whose eaves turn up at the corners.</summary>
        static void Hanok(LandmarkKit k, float x, float z, float w, float d, float baseY, Color32 wall, Color32 col, Color32 tile, Color32 tileDark)
        {
            k.Prism(LandmarkKit.Rect(x, z, w + 3f, d + 3f), 0.35f, baseY + 0.9f, Stone, LM.Solid, 1f, LM.C("#b9a88c"), LM.Paving);
            float y0 = baseY + 0.9f, h = Mathf.Clamp(d * 0.32f, 3.2f, 5f);
            int nc = Mathf.Max(2, Mathf.RoundToInt(w / 4f));
            for (int c = 0; c <= nc; c++)
                foreach (float s in new[] { -1f, 1f })
                { float cx = x - w * 0.5f + c * w / nc, cz = z + s * (d * 0.5f - 0.6f); k.Beam(new Vector3(cx, y0, cz), new Vector3(cx, y0 + h, cz), 0.45f, 0.45f, col, LM.Solid); }
            k.Prism(LandmarkKit.Rect(x, z, w - 2.4f, d - 2.6f), y0, y0 + h - 0.4f, wall, LM.Solid, 1f, wall, -1);
            k.Box(new Vector3(x, y0 + h - 0.2f, z), new Vector3(w + 0.6f, 0.5f, d + 0.6f), 0f, col, LM.Solid, 1f, col, -1);
            // eaves: a thin skirt turned up at the corners, then the hip roof to a short ridge
            float ey = y0 + h + 0.1f, ow = w + 6f, od = d + 6f;
            var eave = new List<Vector2> { new Vector2(x - ow * 0.5f - 1.2f, z - od * 0.5f - 1.2f), new Vector2(x, z - od * 0.5f), new Vector2(x + ow * 0.5f + 1.2f, z - od * 0.5f - 1.2f),
                                           new Vector2(x + ow * 0.5f, z), new Vector2(x + ow * 0.5f + 1.2f, z + od * 0.5f + 1.2f), new Vector2(x, z + od * 0.5f),
                                           new Vector2(x - ow * 0.5f - 1.2f, z + od * 0.5f + 1.2f), new Vector2(x - ow * 0.5f, z) };
            var under = new List<Vector2>(); foreach (var p in eave) under.Add(new Vector2(x + (p.x - x) * 0.82f, z + (p.y - z) * 0.82f));
            k.Loft(under, ey - 0.3f, eave, ey + 0.7f, tileDark, LM.Solid, 1f);
            k.Cap(under, ey - 0.3f, false, tileDark, LM.Solid);
            float rh = d * 0.42f + 1.5f;
            var ridge = new List<Vector2>(); foreach (var p in eave) ridge.Add(new Vector2(x + (p.x - x) * (w * 0.55f / ow), z + (p.y - z) * (1.2f / od)));
            k.Loft(eave, ey + 0.7f, ridge, ey + 0.7f + rh, tile, LM.Metal, 1f);
            k.Cap(ridge, ey + 0.7f + rh, true, tileDark, LM.Roof);
            k.Box(new Vector3(x, ey + 0.95f + rh, z), new Vector3(w * 0.6f, 0.5f, 0.9f), 0f, tileDark, LM.Solid, 1f, tileDark, LM.Roof);
        }

        // ------------------------------------------------------------------ L7 by Lotte: 26-floor hotel on a three-level podium — a stone base
        // with a glazed lobby and a canopy over the drop-off, a slender tower that steps back at the 18th floor, a lit crown with the red sign,
        // roof plant behind it, a garden terrace on the podium roof.
        static void HotelL7(LandmarkKit k)
        {
            Pad(k, 90f, 70f, 8f, Pave);
            // podium: stone ground floor, glazed upper floors, a terrace slab
            k.Prism(LandmarkKit.RoundRect(0, 2f, 70f, 46f, 6f, 3), 0.3f, 5.5f, GlassWarm, LM.Glass, 5.5f, Stone, -1);
            k.Prism(LandmarkKit.RoundRect(0, 2f, 72f, 48f, 6f, 3), 5.5f, 6.4f, Stone, LM.Solid, 1f, Stone, -1);
            k.Prism(LandmarkKit.RoundRect(0, 4f, 68f, 42f, 6f, 3), 6.4f, 13f, GlassBlue, LM.Glass, 3.3f, Stone, LM.Paving);
            k.Prism(LandmarkKit.RoundRect(-20f, 12f, 22f, 16f, 4f, 2), 13f, 13.6f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
            for (int i = 0; i < 4; i++) k.Tree(new Vector3(-27f + i * 4.6f, 13.6f, 12f + (i % 2) * 3f), 4.5f, Leaf, i);
            // canopy over the entrance on the street side (−z), drop-off lane
            k.Box(new Vector3(6f, 5.2f, -26f), new Vector3(26f, 0.6f, 10f), 0f, MetalW, LM.Metal, 1f, MetalW, LM.Roof);
            k.Beam(new Vector3(-5f, 0.3f, -30f), new Vector3(-5f, 4.9f, -30f), 0.35f, 0.35f, Steel, LM.Steel);
            k.Beam(new Vector3(17f, 0.3f, -30f), new Vector3(17f, 4.9f, -30f), 0.35f, 0.35f, Steel, LM.Steel);
            Road(k, new List<Vector2> { new Vector2(-34f, -30f), new Vector2(34f, -30f) }, 3.2f, false, false);
            // tower shaft and the setback
            k.Prism(LandmarkKit.Chamfer(4f, 4f, 40f, 22f, 3f), 13f, 70f, GlassDark, LM.Fins, 3.4f, Roof, -1);
            k.Prism(LandmarkKit.Chamfer(4f, 4f, 41f, 23f, 3f), 70f, 70.8f, White, LM.Solid, 1f, White, LM.Roof);
            k.Prism(LandmarkKit.Chamfer(6f, 4f, 34f, 20f, 3f), 70.8f, 90f, GlassDark, LM.Fins, 3.4f, Roof, -1);
            k.Box(new Vector3(-17f, 41.5f, 4f), new Vector3(3f, 57f, 23f), 0, White, LM.Solid, 3.4f, White, LM.Roof);     // the white spine
            k.Box(new Vector3(-11.5f, 80.4f, 4f), new Vector3(3f, 19.2f, 21f), 0, White, LM.Solid, 3.4f, White, LM.Roof);
            // crown: a lit glass lantern, the sign, roof plant behind the screen
            k.Prism(LandmarkKit.Chamfer(6f, 4f, 34f, 20f, 3f), 90f, 96f, Warm, LM.Light, 1f, Roof, LM.Roof);
            k.Prism(LandmarkKit.Chamfer(6f, 4f, 35f, 21f, 3f), 96f, 97f, White, LM.Solid, 1f, White, -1);
            k.Box(new Vector3(6f, 93f, 4f - 10.7f), new Vector3(10f, 4f, 0.6f), 0, Red, LM.Light, 1f, Red, LM.Light);
            k.Box(new Vector3(10f, 97.9f, 6f), new Vector3(9f, 1.8f, 6f), 0f, MetalG, LM.Metal, 1.8f, MetalD, LM.Metal);
            k.Box(new Vector3(0f, 97.6f, 6f), new Vector3(5f, 1.2f, 5f), 0f, MetalG, LM.Metal, 1.2f, MetalD, LM.Metal);
            Trees(k, -38f, -33f, 38f, -33f, 9.5f, 7f, 5f);
            Trees(k, 40f, -20f, 40f, 26f, 9f, 7f, 6f);
        }

        // ------------------------------------------------------------------ logistics park: class A warehouses (roof lights, roof plant, dock
        // doors with levellers and canopies), truck courts with trailers at the docks and in a waiting row, a staff car park by the office,
        // the gatehouse with barriers at the entrance.
        static void Logistics(LandmarkKit k, int halls, float L, float D)
        {
            float span = D + 70f; float pw = L + 80f, pd = halls * span + 60f;
            Pad(k, pw, pd, 10f, Asph);
            for (int h = 0; h < halls; h++)
            {
                float cz = (h - (halls - 1) * 0.5f) * span;
                k.Prism(LandmarkKit.Rect(0, cz, L, D), 0.3f, 14f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
                k.Prism(LandmarkKit.Rect(0, cz, L + 0.8f, D + 0.8f), 14f, 14.9f, MetalG, LM.Metal, 1f, Roof, -1);
                k.Box(new Vector3(0, 13.2f, cz - D * 0.5f - 0.3f), new Vector3(L, 1.6f, 0.4f), 0, LM.C("#e0261b"), LM.Solid, 3f, Red, LM.Roof);
                // roof lights in bands and roof plant
                for (float x = -L * 0.5f + 20f; x < L * 0.5f - 15f; x += 24f)
                    k.Box(new Vector3(x, 14.35f, cz), new Vector3(2.2f, 0.6f, D - 24f), 0f, MetalG, LM.Metal, 1f, LM.C("#aab4bd"), LM.Glass);
                for (int i = 0; i < 3; i++) k.Box(new Vector3(-L * 0.25f + i * L * 0.25f, 15.4f, cz + D * 0.32f), new Vector3(6f, 1.8f, 3.5f), 0f, MetalG, LM.Metal, 1.8f, MetalD, LM.Metal);
                // dock doors with canopies; trailers backed onto most of them
                int doors = Mathf.FloorToInt(L / 8f) - 4;
                k.Box(new Vector3(0f, 5.4f, cz - D * 0.5f - 1.6f), new Vector3(doors * 8f, 0.3f, 3.2f), 0f, MetalG, LM.Metal, 1f, MetalG, LM.Roof);
                for (int i = 0; i < doors; i++)
                {
                    float x = -L * 0.5f + 16f + i * 8f;
                    k.Box(new Vector3(x, 2.6f, cz - D * 0.5f - 0.25f), new Vector3(3f, 3.2f, 0.3f), 0, Steel, LM.Steel, 1f, Steel, LM.Steel);
                    if (Mathf.Abs(Mathf.Sin(i * 1.93f + h * 5.1f)) > 0.38f) Truck(k, new Vector3(x, 0.3f, cz - D * 0.5f - 9.5f), 90f, (i % 5 == 0) ? LM.C("#2f4f7a") : White);
                }
                // truck court markings
                for (int i = 0; i <= doors; i++)
                {
                    float x = -L * 0.5f + 12f + i * 8f;
                    k.Box(new Vector3(x, 0.32f, cz - D * 0.5f - 10f), new Vector3(0.15f, 0.03f, 16f), 0f, LotLine, LM.Solid, 1f, LotLine, LM.Light);
                }
                // office on the back corner
                k.Prism(LandmarkKit.RoundRect(-L * 0.5f + 20f, cz + D * 0.5f + 8f, 34f, 14f, 3f, 2), 0.3f, 9f, GlassBlue, LM.Glass, 3.4f, Roof, LM.Roof);
                k.Box(new Vector3(-L * 0.5f + 20f, 9.4f, cz + D * 0.5f + 8f), new Vector3(36f, 0.8f, 16f), 0f, White, LM.Solid, 1f, White, LM.Roof);
            }
            // staff car park beside the office at the back of the last hall, waiting trailers along the side, the gatehouse at the front corner
            float backZ = (halls - 1) * 0.5f * span + D * 0.5f;
            Lot(k, -L * 0.5f + 42f, -L * 0.5f + 42f + Mathf.Min(120f, L * 0.4f), backZ + 2f, Mathf.Min(backZ + 38f, pd * 0.5f - 4f), 0.75f, 31f);
            for (int i = 0; i < 6; i++) Truck(k, new Vector3(L * 0.5f + 22f, 0.3f, -halls * span * 0.5f + 30f + i * 6f), 0f, i % 3 == 0 ? LM.C("#2f4f7a") : White);
            float gx = L * 0.5f + 20f, gz = -pd * 0.5f + 14f;
            k.Prism(LandmarkKit.RoundRect(gx, gz, 8f, 5f, 1f, 2), 0.3f, 3.4f, GlassBlue, LM.Glass, 3.2f, White, LM.Roof);
            k.Box(new Vector3(gx, 3.8f, gz), new Vector3(14f, 0.4f, 10f), 0f, White, LM.Solid, 1f, White, LM.Roof);
            for (int s = -1; s <= 1; s += 2) k.Beam(new Vector3(gx - 9f, 1.1f, gz + s * 4f), new Vector3(gx - 17f, 1.1f, gz + s * 4f), 0.15f, 0.15f, Red, LM.Solid);
            // perimeter fence
            var f = LandmarkKit.Rect(0, 0, pw - 4f, pd - 4f);
            for (int i = 0; i < 4; i++) { var a = f[i]; var b = f[(i + 1) % 4]; k.Beam(new Vector3(a.x, 1.2f, a.y), new Vector3(b.x, 1.2f, b.y), 0.08f, 2f, MetalD, LM.Steel); }
        }
    }
}
