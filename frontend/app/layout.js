import Link from "next/link";
import "./globals.css";
import "leaflet/dist/leaflet.css";

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        <nav style={{ padding: "20px", background: "#eee" }}>
          <Link href="/request">Request Ride</Link> |{" "}
          <Link href="/wallet">Wallet</Link>
        </nav>

        {children}
      </body>
    </html>
  );
}