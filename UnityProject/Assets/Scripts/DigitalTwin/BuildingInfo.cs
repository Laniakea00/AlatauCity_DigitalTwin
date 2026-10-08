namespace AlatauCity.DigitalTwin
{
    /// <summary>Digital-twin passport of one building (row of buildings.csv). Bid = id used in meshes (uv2.y - 1).</summary>
    [System.Serializable]
    public class BuildingInfo
    {
        public int Bid; public string Id, District, Kind, Use, Source, Parcel; public int Year, Floors;
        public float HeightM, GfaM2, GroundM, X, Z; public double Easting, Northing;   // EPSG:32643 (UTM 43N)
        // live data slots (IoT / GIS / BIM feeds)
        public float EnergyKw, WaterM3h; public int Occupancy; public string Status;
    }
}
