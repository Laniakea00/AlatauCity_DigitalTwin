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

        // ------------------------------------------------------------------ K-Park (10 ha, owner 05.11.2026: «улучши парк, как он должен
        // быть красивым»; content after the Association of Koreans of Kazakhstan: park zones, a cultural and business centre for conferences
        // and exhibitions, a library with an interactive museum, a 65 m observation tower; 2027, 90 years of the Koryo-saram). Local +z is
        // north, the main gate is on the south side:
        //   south  — entrance plaza with an iljumun gate, haetae guardians, mugunghwa beds and the name stone;
        //   axis   — a cherry-blossom alley to the central plaza with the observation tower (a slim core, a glass deck at 56 m, spire to 65 m);
        //   west   — the cultural and business centre: a long hall under a tiled roof with lifted eaves, glass front to the plaza;
        //   east   — the library and interactive museum: a white two-storey block with a roof garden and a hanok porch;
        //   north  — the Korean garden: a lotus pond with an island pavilion and an arched bridge, a stone pagoda, a rock garden,
        //            pine groves and a tea house; north-east a festival lawn with a small amphitheatre; south-east a playground.
        // The park lies flush with the ground (the earth slab under it shows grass at its edge, not a dark plinth).
        static void KPark(LandmarkKit k)
        {
            var paveK = LM.C("#d6cdb9"); var paveK2 = LM.C("#b9ad95"); var col = LM.C("#8c2f22"); var wall = LM.C("#efe9dc"); var tile = LM.C("#4b5058"); var tileDark = LM.C("#3c4047");
            var sakura = LM.C("#f1b6cb"); var sakura2 = LM.C("#e99ab6"); var pine = LM.C("#2f5a35"); var mugung = LM.C("#c85a9a"); var rock = LM.C("#8f8a80");
            var lawn = LM.C("#6f9150"); var deck = LM.C("#9c7a52"); var hedge = LM.C("#3f6532"); var glassK = LM.C("#3b5a6e"); var tower = LM.C("#e8e6e0");
            k.Planted = true;
            // the earth under the park: its sides are grass, its top the lawn, 0.25 m over the ground
            k.Prism(LandmarkKit.RoundRect(0, 0, 360f, 280f, 50f, 6), -12f, 0.25f, LM.C("#5d7d45"), LM.Plant, 3f, lawn, LM.Plant, false, LandmarkKit.GreenTag);
            // a clipped hedge round the edge, open at the south gate and at three side gates
            var hO = LandmarkKit.RoundRect(0, 0, 356f, 276f, 48f, 6); var hI = LandmarkKit.RoundRect(0, 0, 350f, 270f, 45f, 6);
            for (int i = 0; i < hI.Count; i++)
            {
                int j = (i + 1) % hI.Count; var m = (hI[i] + hI[j]) * 0.5f;
                if ((Mathf.Abs(m.x) < 22f && m.y < 0f) || (Mathf.Abs(m.y + 10f) < 14f && Mathf.Abs(m.x) > 150f) || (Mathf.Abs(m.x - 60f) < 12f && m.y > 0f)) continue;
                k.Prism(new List<Vector2> { hI[i], hI[j], hO[j], hO[i] }, 0.25f, 1.6f, hedge, LM.Plant, 1f, hedge, LM.Plant, false, 1f);
            }
            // ring walk inside the hedge
            var ringO = LandmarkKit.RoundRect(0, 0, 334f, 254f, 40f, 6); var ringI = LandmarkKit.RoundRect(0, 0, 326f, 246f, 36f, 6);
            Band(k, ringI, ringO, 0.25f, 0.4f, paveK2, paveK, LM.Paving, LandmarkKit.GreenTag);

            // ---- south: entrance plaza, the gate, the guardians, beds and the name stone
            k.Prism(LandmarkKit.RoundRect(0f, -120f, 84f, 34f, 14f, 4), 0.25f, 0.42f, paveK2, LM.Solid, 1f, paveK, LM.Paving);
            for (int s = -1; s <= 1; s += 2)
            {
                for (int c = 0; c < 2; c++) k.Beam(new Vector3(s * (5f + c * 7f), 0.42f, -126f), new Vector3(s * (5f + c * 7f), 8.6f, -126f), 0.9f, 0.9f, col, LM.Solid);
                k.Box(new Vector3(s * 16f, 1.4f, -138f), new Vector3(2.2f, 2f, 3f), 0f, rock, LM.Solid, 1f, rock, LM.Solid);           // haetae on plinths
                k.Box(new Vector3(s * 16f, 3.0f, -138.5f), new Vector3(1.6f, 1.4f, 1.8f), 0f, LM.C("#a39d92"), LM.Solid, 1f, LM.C("#a39d92"), LM.Solid);
                for (int b = 0; b < 3; b++)
                    k.Prism(LandmarkKit.RoundRect(s * (28f + b * 9f), -122f, 7f, 16f, 3f, 2), 0.42f, 0.85f, Stone, LM.Solid, 1f, b == 1 ? LM.C("#e3b23c") : mugung, LM.Plant);
            }
            k.Box(new Vector3(0f, 8.9f, -126f), new Vector3(30f, 0.6f, 5.2f), 0f, col, LM.Solid, 1f, col, LM.Solid);
            k.Loft(LandmarkKit.Rect(0f, -126f, 34f, 8f), 9.2f, LandmarkKit.Rect(0f, -126f, 24f, 1.0f), 12.2f, tile, LM.Metal, 1f);
            k.Box(new Vector3(0f, 12.35f, -126f), new Vector3(25f, 0.4f, 1.1f), 0f, tileDark, LM.Solid, 1f, tileDark, LM.Roof);
            k.Box(new Vector3(-30f, 1.0f, -134f), new Vector3(9f, 1.6f, 1.6f), 0f, rock, LM.Solid, 1f, LM.C("#6e695f"), LM.Solid);  // name stone

            // ---- the axis: a cherry alley from the gate to the central plaza, and a cross walk to the two buildings
            k.Prism(LandmarkKit.Rect(0f, -78f, 12f, 76f), 0.25f, 0.42f, paveK2, LM.Solid, 1f, paveK, LM.Paving);
            k.Prism(LandmarkKit.Rect(0f, -40f, 200f, 8f), 0.25f, 0.4f, paveK2, LM.Solid, 1f, paveK, LM.Paving);
            k.Prism(LandmarkKit.Rect(0f, 40f, 6f, 88f), 0.25f, 0.4f, paveK2, LM.Solid, 1f, paveK, LM.Paving);
            for (int i = 0; i < 8; i++)
            {
                float z = -110f + i * 9.5f;
                foreach (float s in new[] { -1f, 1f })
                {
                    k.Tree(new Vector3(s * 10f, 0.42f, z), 6.5f + (i % 3) * 0.6f, (i & 1) == 0 ? sakura : sakura2, i * 1.3f + s);
                    if (i % 2 == 0) k.Box(new Vector3(s * 7.2f, 1.0f, z + 4.7f), new Vector3(0.7f, 1.3f, 0.7f), 0f, Stone, LM.Solid, 1f, Warm, LM.Light);  // stone lanterns
                }
            }
            // central plaza: a round paved court with a ring of benches and the tower in its middle
            k.Prism(LandmarkKit.Circle(0f, -12f, 30f, 40), 0.25f, 0.45f, paveK2, LM.Solid, 1f, paveK, LM.Paving);
            k.Prism(LandmarkKit.Circle(0f, -12f, 13f, 32), 0.45f, 0.5f, Stone, LM.Solid, 1f, LM.C("#c9bfa9"), LM.Paving);
            for (int i = 0; i < 12; i++)
            {
                float a = i * Mathf.PI * 2f / 12f; if (Mathf.Abs(Mathf.Sin(a) + 1f) < 0.2f) continue;
                k.Box(new Vector3(Mathf.Cos(a) * 24f, 0.75f, -12f + Mathf.Sin(a) * 24f), new Vector3(3.2f, 0.45f, 0.8f), -a * Mathf.Rad2Deg + 90f, deck, LM.Solid, 1f, deck, LM.Solid);
            }
            // the observation tower, 65 m: a tapering white core, four fins, a glass ring deck at 56 m under a disc roof, a spire
            k.Tube(new Vector3(0f, 0.5f, -12f), new Vector3(0f, 54f, -12f), 4.2f, 2.8f, 16, tower, LM.Solid);
            for (int f = 0; f < 4; f++)
            {
                float a = f * 90f * Mathf.Deg2Rad + 0.785f; var dir = new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a));
                k.Slab(new Vector3(0f, 0.5f, -12f) + dir * 3.8f, new Vector3(0f, 0.5f, -12f) + dir * 9f, new Vector3(0f, 18f, -12f) + dir * 3.3f, new Vector3(0f, 30f, -12f) + dir * 3.2f, 0.5f, tower, LM.Solid);
            }
            k.Cylinder(new Vector3(0f, 53.5f, -12f), 9.5f, 0.8f, 24, tower, LM.Solid, 1f, tower, LM.Solid);
            k.Cylinder(new Vector3(0f, 54.3f, -12f), 9.0f, 4.2f, 24, glassK, LM.Glass, 1f, tower, LM.Solid);
            k.Cylinder(new Vector3(0f, 58.5f, -12f), 10.5f, 0.6f, 24, col, LM.Solid, 1f, tile, LM.Roof, 1.2f);
            k.Tube(new Vector3(0f, 60f, -12f), new Vector3(0f, 65f, -12f), 0.5f, 0.1f, 8, Stone, LM.Steel);
            k.Box(new Vector3(0f, 2.6f, -12f), new Vector3(12f, 4.2f, 12f), 45f, glassK, LM.Glass, 1f, tower, LM.Roof);        // ticket pavilion at its foot

            // ---- west: the cultural and business centre (conference hall and exhibitions), a long hanok hall with a glass front
            k.Prism(LandmarkKit.Rect(-102f, -60f, 96f, 52f), 0.25f, 0.5f, paveK2, LM.Solid, 1f, paveK, LM.Paving);
            k.Box(new Vector3(-102f, 4.6f, -60f), new Vector3(76f, 8.4f, 30f), 0f, wall, LM.Solid, 2f, wall, LM.Roof);
            k.Box(new Vector3(-102f, 4.2f, -44.9f), new Vector3(68f, 6.8f, 0.2f), 0f, glassK, LM.Glass, 1f, glassK, LM.Glass);
            Hanok(k, -102f, -60f, 80f, 34f, 0.5f, wall, col, tile, tileDark);
            // ---- east: library and interactive museum, two storeys, a roof garden and a red porch toward the axis
            k.Prism(LandmarkKit.Rect(102f, -60f, 92f, 52f), 0.25f, 0.5f, paveK2, LM.Solid, 1f, paveK, LM.Paving);
            k.Box(new Vector3(104f, 5.2f, -62f), new Vector3(66f, 9.4f, 32f), 0f, wall, LM.Solid, 2f, wall, LM.Roof);
            k.Box(new Vector3(104f, 3.2f, -45.9f), new Vector3(58f, 4.6f, 0.2f), 0f, glassK, LM.Glass, 1f, glassK, LM.Glass);
            k.Box(new Vector3(104f, 8.0f, -45.9f), new Vector3(58f, 2.2f, 0.2f), 0f, glassK, LM.Glass, 1f, glassK, LM.Glass);
            k.Prism(LandmarkKit.Rect(104f, -62f, 60f, 26f), 9.9f, 10.4f, Stone, LM.Solid, 1f, LM.C("#5f8a46"), LM.Plant);         // roof garden
            for (int i = 0; i < 6; i++) k.Tree(new Vector3(80f + i * 9.5f, 10.4f, -62f + (i % 2) * 6f - 3f), 4f, Leaf2, i * 0.7f);
            Hanok(k, 104f, -40f, 22f, 8f, 0.5f, wall, col, tile, tileDark);

            // ---- north: the Korean garden — a lotus pond, an island pavilion, an arched bridge, a pagoda, a rock garden, a tea house
            List<Vector2> Shore(float grow)
            {
                var l = new List<Vector2>();
                for (int i = 0; i < 56; i++)
                {
                    float a = i * Mathf.PI * 2f / 56f;
                    float r = 1f + 0.14f * Mathf.Sin(2f * a + 0.6f) + 0.08f * Mathf.Sin(3f * a + 1.9f) - 0.05f * Mathf.Cos(5f * a);
                    l.Add(new Vector2(-62f + Mathf.Cos(a) * (64f * r + grow), 64f + Mathf.Sin(a) * (36f * r + grow)));
                }
                return l;
            }
            k.Prism(Shore(5f), 0.25f, 0.4f, GrassDark, LM.Solid, 1f, LM.C("#6f8a46"), LM.Plant);
            k.Prism(Shore(1.4f), 0.25f, 0.5f, rock, LM.Solid, 1f, LM.C("#a8a196"), LM.Paving);
            k.Prism(Shore(0f), 0.25f, 0.52f, rock, LM.Solid, 1f, Water, LM.Water);
            k.Prism(LandmarkKit.Circle(-52f, 70f, 13f, 18), 0.25f, 0.95f, rock, LM.Solid, 1f, Grass, LM.Plant);
            for (int i = 0; i < 14; i++)                                                                                    // lotus pads
            {
                float a = i * 2.39f, rr = 18f + (i % 4) * 7f;
                k.Cylinder(new Vector3(-80f + Mathf.Cos(a) * rr * 0.7f, 0.54f, 56f + Mathf.Sin(a) * rr * 0.35f), 1.8f, 0.05f, 8, LM.C("#4f7d3a"), LM.Plant, 1f, (i % 3 == 0) ? LM.C("#f3b8cf") : LM.C("#4f7d3a"), LM.Plant);
            }
            for (int i = 0; i < 10; i++)                                                                                    // arched bridge to the island
            {
                float t0 = i / 10f, t1 = (i + 1) / 10f; float xa = Mathf.Lerp(-30f, -42f, t0), xb = Mathf.Lerp(-30f, -42f, t1);
                float za = Mathf.Lerp(32f, 60f, t0), zb = Mathf.Lerp(32f, 60f, t1);
                float ya = 0.9f + Mathf.Sin(t0 * Mathf.PI) * 2.4f, yb = 0.9f + Mathf.Sin(t1 * Mathf.PI) * 2.4f;
                k.Slab(new Vector3(xa - 1.8f, ya, za), new Vector3(xb - 1.8f, yb, zb), new Vector3(xb + 1.8f, yb, zb), new Vector3(xa + 1.8f, ya, za), 0.35f, col, LM.Solid);
            }
            Hanok(k, -52f, 70f, 11f, 11f, 0.95f, wall, col, tile, tileDark);                                               // island pavilion (jeongja)
            Hanok(k, -136f, 92f, 24f, 13f, 0.4f, wall, col, tile, tileDark);                                               // tea house
            // five-storey stone pagoda on a small mound
            k.Prism(LandmarkKit.Circle(28f, 96f, 9f, 16), 0.25f, 1.2f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
            for (int s = 0; s < 5; s++)
            {
                float w = 4.6f - s * 0.55f, y = 1.2f + s * 2.1f;
                k.Box(new Vector3(28f, y + 0.7f, 96f), new Vector3(w * 0.7f, 1.4f, w * 0.7f), 0f, LM.C("#b7b0a3"), LM.Solid, 1f, LM.C("#b7b0a3"), LM.Solid);
                k.Box(new Vector3(28f, y + 1.65f, 96f), new Vector3(w, 0.5f, w), 0f, LM.C("#9e978a"), LM.Solid, 1f, LM.C("#9e978a"), LM.Solid);
            }
            k.Tube(new Vector3(28f, 11.7f, 96f), new Vector3(28f, 14.2f, 96f), 0.35f, 0.15f, 8, LM.C("#8d8578"), LM.Solid);
            // rock garden: raked gravel with standing stones
            k.Prism(LandmarkKit.RoundRect(-10f, 104f, 40f, 18f, 6f, 3), 0.25f, 0.38f, Stone, LM.Solid, 1f, LM.C("#ddd7ca"), LM.Paving);
            for (int i = 0; i < 5; i++) k.Box(new Vector3(-24f + i * 7f, 1.1f, 103f + (i % 2) * 3f), new Vector3(2.4f - (i % 3) * 0.4f, 1.6f + (i % 2) * 0.8f, 2f), i * 23f, rock, LM.Solid, 1f, rock, LM.Solid);
            // ---- north-east: the festival lawn and a half-ring amphitheatre facing a small stage
            for (int r = 0; r < 5; r++)
                k.Prism(Sector(new Vector2(118f, 66f), 16f + r * 4.5f, 19.5f + r * 4.5f, 200f, 340f), 0.25f, 0.6f + r * 0.45f, Stone, LM.Solid, 1f, LM.C("#cdc4b2"), LM.Paving);
            k.Prism(LandmarkKit.Circle(118f, 66f, 11f, 24), 0.25f, 0.9f, Stone, LM.Solid, 1f, deck, LM.Paving);
            k.Loft(LandmarkKit.Rect(118f, 74f, 22f, 6f), 6.5f, LandmarkKit.Rect(118f, 74f, 16f, 1f), 8.2f, tile, LM.Metal, 1f);
            for (int s = -1; s <= 1; s += 2) k.Beam(new Vector3(118f + s * 9.5f, 0.9f, 74f), new Vector3(118f + s * 9.5f, 6.5f, 74f), 0.6f, 0.6f, col, LM.Solid);
            // ---- south-east: the children's playground on soft red rubber
            k.Prism(LandmarkKit.RoundRect(132f, -6f, 40f, 34f, 8f, 3), 0.25f, 0.4f, Stone, LM.Solid, 1f, LM.C("#c4473a"), LM.Solid);
            var toy = new[] { LM.C("#f2c230"), LM.C("#2f8fd8"), LM.C("#e0261b"), LM.C("#5cbf48") };
            for (int i = 0; i < 6; i++) k.Box(new Vector3(118f + (i % 3) * 13f, 1.6f, -14f + (i / 3) * 15f), new Vector3(4f, 2.6f + (i % 2), 3f), i * 30f, toy[i % 4], LM.Solid, 1f, toy[(i + 1) % 4], LM.Solid);

            // ---- trees: pine groves and cherry clumps on the lawns, clear of the walks, water and buildings
            bool Free(float x, float z)
            {
                float u = x / 160f, v = z / 120f; if (u * u + v * v > 0.88f) return false;
                if (Mathf.Abs(x) < 18f && z < 90f) return false;                                     // axis and the north walk
                if (Mathf.Abs(z + 40f) < 10f && Mathf.Abs(x) < 104f) return false;                   // cross walk
                if (x * x + (z + 12f) * (z + 12f) < 36f * 36f) return false;                          // central plaza
                if (Mathf.Abs(x + 102f) < 52f && Mathf.Abs(z + 60f) < 30f) return false;             // cultural centre
                if (Mathf.Abs(x - 102f) < 50f && Mathf.Abs(z + 58f) < 32f) return false;             // museum
                if (Mathf.Abs(z + 120f) < 22f && Mathf.Abs(x) < 70f) return false;                   // entrance plaza
                float px = (x + 62f) / 76f, pz = (z - 64f) / 46f; if (px * px + pz * pz < 1f) return false;     // pond
                if (Mathf.Abs(x - 118f) < 36f && Mathf.Abs(z - 62f) < 28f) return false;             // amphitheatre
                if (Mathf.Abs(x - 132f) < 26f && Mathf.Abs(z + 6f) < 22f) return false;              // playground
                if (Mathf.Abs(x - 28f) < 13f && Mathf.Abs(z - 96f) < 13f) return false;              // pagoda
                if (Mathf.Abs(x + 10f) < 24f && Mathf.Abs(z - 104f) < 12f) return false;             // rock garden
                if (Mathf.Abs(x + 136f) < 18f && Mathf.Abs(z - 92f) < 12f) return false;             // tea house
                return true;
            }
            int n = 0;
            for (float x = -158f; x <= 158f; x += 8.5f)
                for (float z = -122f; z <= 122f; z += 8.5f)
                {
                    float h = Mathf.Abs(Mathf.Sin(x * 0.173f + z * 0.311f) * Mathf.Cos(x * 0.051f - z * 0.087f));
                    if (h < 0.42f) continue;                                                           // groves, with open lawns between
                    float jx = x + Mathf.Sin(z * 1.7f + x) * 3f, jz = z + Mathf.Cos(x * 1.3f - z) * 3f;
                    if (!Free(jx, jz)) continue;
                    float kind = Hash(jx, jz);
                    if (kind < 0.30f) k.Tree(new Vector3(jx, 0.25f, jz), 6f + h * 2f, kind < 0.15f ? sakura : sakura2, n * 0.37f);
                    else if (kind < 0.62f) k.Tree(new Vector3(jx, 0.25f, jz), 9f + h * 6f, pine, n * 0.41f);
                    else ParkTree(k, jx, jz, 8f + h * 6f, n);
                    n++;
                }
            // trees along the ring walk, cherry and green in turn; lamps between them
            for (int i = 0; i < 72; i++)
            {
                float a = i * Mathf.PI * 2f / 72f; float x = Mathf.Cos(a) * 158f, z = Mathf.Sin(a) * 119f;
                if (Mathf.Abs(x) < 26f && z < 0f) continue;
                k.Tree(new Vector3(x, 0.4f, z), 8.5f, i % 3 == 0 ? sakura : (i & 1) == 0 ? Leaf : Leaf2, i);
                if (i % 2 == 1)
                {
                    float xl = Mathf.Cos(a) * 150f, zl = Mathf.Sin(a) * 112f;
                    k.Beam(new Vector3(xl, 0.4f, zl), new Vector3(xl, 4.2f, zl), 0.12f, 0.12f, LM.C("#3a3d42"), LM.Steel);
                    k.Box(new Vector3(xl, 4.35f, zl), new Vector3(0.6f, 0.4f, 0.6f), 0f, Warm, LM.Light, 1f, Warm, LM.Light);
                }
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
