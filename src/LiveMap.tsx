import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { useEffect } from "react";
import type { Listing, NetworkSnapshot } from "./api";

const donorIcon = new L.DivIcon({ className: "map-pin donor-pin", html: '<span class="pin-dot"></span>', iconSize: [20, 20], iconAnchor: [10, 10] });
const recipientIcon = new L.DivIcon({ className: "map-pin recipient-pin", html: '<span class="pin-dot"></span>', iconSize: [20, 20], iconAnchor: [10, 10] });
const volunteerIcon = new L.DivIcon({ className: "map-pin volunteer-pin", html: '<span class="pin-dot">↗</span>', iconSize: [24, 24], iconAnchor: [12, 12] });
const center: [number, number] = [12.9716, 77.5946];
const recipients: [number, number][] = [[12.9675, 77.601], [12.9805, 77.588]];
const volunteers: [number, number][] = [[12.9731, 77.598]];

function FitMap() {
  const map = useMap();
  useEffect(() => { map.invalidateSize(); }, [map]);
  return null;
}

export default function LiveMap({ listings, network }: { listings: Listing[]; network: NetworkSnapshot | null }) {
  const donorLocations = network?.locations.filter((item) => item.kind === "donor") ?? listings
    .filter((item) => item.latitude != null && item.longitude != null)
    .map((item) => ({ id: String(item.id), name: item.donor_name ?? item.title, kind: "donor" as const, latitude: item.latitude!, longitude: item.longitude! }));
  const recipientLocations = network?.locations.filter((item) => item.kind === "recipient");
  const volunteerLocations = network?.locations.filter((item) => item.kind === "volunteer");
  return <div className="map-canvas">
    <MapContainer center={center} zoom={14} scrollWheelZoom={false} zoomControl={false}>
      <FitMap />
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {donorLocations.map((item) => <Marker key={item.id} position={[item.latitude, item.longitude]} icon={donorIcon}><Popup>{item.name}</Popup></Marker>)}
      {(recipientLocations ?? recipients.map((position, index) => ({ id: `recipient-${index}`, name: index === 0 ? "Sunrise Care Home" : "Little Steps Foundation", kind: "recipient" as const, latitude: position[0], longitude: position[1] }))).map((item) => <Marker key={item.id} position={[item.latitude, item.longitude]} icon={recipientIcon}><Popup>{item.name}</Popup></Marker>)}
      {(volunteerLocations ?? volunteers.map((position, index) => ({ id: `volunteer-${index}`, name: "Active volunteer · en route", kind: "volunteer" as const, latitude: position[0], longitude: position[1] }))).map((item) => <Marker key={item.id} position={[item.latitude, item.longitude]} icon={volunteerIcon}><Popup>{item.name}</Popup></Marker>)}
      {(network?.routes ?? [
        { id: 1, points: [center, volunteers[0], recipients[0]] },
        { id: 2, points: [center, recipients[1]] },
      ]).map((route) => <Polyline key={route.id} positions={route.points} pathOptions={{ color: "#f0a552", weight: 3, dashArray: "7 8" }} />)}
    </MapContainer>
    <div className="map-legend"><span><i className="legend-donor" />Donors</span><span><i className="legend-recipient" />Recipients</span><span><i className="legend-volunteer" />Volunteers</span></div>
    <div className="map-live"><span className="live-dot" /> Updating live</div>
  </div>;
}
