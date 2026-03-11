"use client";

import { useState, useEffect } from "react";
import api from "../../lib/api";
import dynamic from "next/dynamic";
import "leaflet/dist/leaflet.css";

/* Disable SSR for map components */
const MapContainer = dynamic(
  () => import("react-leaflet").then((mod) => mod.MapContainer),
  { ssr: false }
);

const TileLayer = dynamic(
  () => import("react-leaflet").then((mod) => mod.TileLayer),
  { ssr: false }
);

const Marker = dynamic(
  () => import("react-leaflet").then((mod) => mod.Marker),
  { ssr: false }
);

const Popup = dynamic(
  () => import("react-leaflet").then((mod) => mod.Popup),
  { ssr: false }
);

export default function RequestRide() {

  const [pickupLat, setPickupLat] = useState("");
  const [pickupLng, setPickupLng] = useState("");
  const [dropLat, setDropLat] = useState("");
  const [dropLng, setDropLng] = useState("");
  const [loading, setLoading] = useState(false);

  const [driverLocation, setDriverLocation] = useState(null);
  const [driverIcon, setDriverIcon] = useState(null);

  /* Load Leaflet icon only on client */
  useEffect(() => {

    import("leaflet").then((L) => {

      const icon = new L.Icon({
        iconUrl: "https://cdn-icons-png.flaticon.com/512/684/684908.png",
        iconSize: [35, 35],
      });

      setDriverIcon(icon);

    });

  }, []);

  /* WebSocket connection */
  useEffect(() => {

    const socket = new WebSocket("ws://localhost:8000/ws/driver_location");

    socket.onopen = () => {
      console.log("Connected to driver location updates");
    };

    socket.onmessage = (event) => {

      try {

        const data = JSON.parse(event.data);

        if (data.type === "driver_location") {

          setDriverLocation({
            lat: data.lat,
            lng: data.lng
          });

        }

      } catch (error) {
        console.log("Non JSON message:", event.data);
      }

    };

    socket.onerror = (err) => {
      console.log("WebSocket error:", err);
    };

    socket.onclose = () => {
      console.log("WebSocket disconnected");
    };

    return () => socket.close();

  }, []);

  /* Request ride API */
  const requestRide = async () => {

    setLoading(true);

    try {

      const res = await api.post("/rides/request", {
        pickup_lat: parseFloat(pickupLat),
        pickup_lng: parseFloat(pickupLng),
        drop_lat: parseFloat(dropLat),
        drop_lng: parseFloat(dropLng),
      });

      alert("Ride created: " + res.data.id);

    } catch (err) {

      console.log(err.response?.data);
      alert(JSON.stringify(err.response?.data));

    }

    setLoading(false);

  };

  return (

    <div style={{ padding: "40px", maxWidth: "700px", margin: "auto" }}>

      <h1>Request Ride</h1>

      <input
        placeholder="Pickup Latitude"
        value={pickupLat}
        onChange={(e) => setPickupLat(e.target.value)}
      />

      <input
        placeholder="Pickup Longitude"
        value={pickupLng}
        onChange={(e) => setPickupLng(e.target.value)}
      />

      <input
        placeholder="Drop Latitude"
        value={dropLat}
        onChange={(e) => setDropLat(e.target.value)}
      />

      <input
        placeholder="Drop Longitude"
        value={dropLng}
        onChange={(e) => setDropLng(e.target.value)}
      />

      <br />
      <br />

      <button onClick={requestRide} disabled={loading}>
        {loading ? "Requesting..." : "Request Ride"}
      </button>

      <div style={{ marginTop: "30px" }}>

        <MapContainer
          center={[9.9816, 76.2999]}
          zoom={13}
          style={{ height: "400px", width: "100%" }}
        >

          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {driverLocation && driverIcon && (

            <Marker
              position={[driverLocation.lat, driverLocation.lng]}
              icon={driverIcon}
            >

              <Popup>Driver Location</Popup>

            </Marker>

          )}

        </MapContainer>

      </div>

    </div>

  );

}