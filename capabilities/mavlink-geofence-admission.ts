// killinchu/capabilities/mavlink-geofence-admission.ts
// INN-09: MAVLinkValidateGeofence — FAA RID geofence enforcement.
// Lean backing: PARTIAL (rejection theorem proven; Float boundary sorry).
// Lutar/Innovations/MAVLinkValidateGeofence.lean at feat/innovations-inn-01-12.
// Doctrine v11 LOCKED 749/14/163 c7c0ba17.
// RECOMMEND ONLY — do not wire to production Pepr without UDS team review.
import { Capability, a } from "pepr";

// DC operational geofence [38.8,39.0] × [-77.2,-76.8]
// TODO(operator): replace with mission-specific geofence per deployment
const GEOFENCE = { lat_min: 38.8, lat_max: 39.0, lon_min: -77.2, lon_max: -76.8 };

export const MAVLinkGeofenceAdmission = new Capability({
  name: "mavlink-geofence-admission",
  description: "Blocks drone telemetry outside FAA RID geofence. INN-09 Doctrine v11.",
  namespaces: ["szl-killinchu"],
});

const { When } = MAVLinkGeofenceAdmission;

When(a.ConfigMap)
  .IsCreatedOrUpdated()
  .WithLabel("szl.io/telemetry-type", "drone")
  .Validate((cm) => {
    const lat = parseFloat(cm.Raw?.data?.["lat"] ?? "NaN");
    const lon = parseFloat(cm.Raw?.data?.["lon"] ?? "NaN");
    if (isNaN(lat) || isNaN(lon)) {
      return cm.Deny("Drone telemetry: lat/lon must be numeric. INN-09.");
    }
    const { lat_min, lat_max, lon_min, lon_max } = GEOFENCE;
    if (lat < lat_min || lat > lat_max || lon < lon_min || lon > lon_max) {
      return cm.Deny(
        `Drone outside geofence: lat=${lat}, lon=${lon}. Expected lat∈[${lat_min},${lat_max}], lon∈[${lon_min},${lon_max}]. FAA RID. INN-09.`
      );
    }
    return cm.Approve();
  });
