"use client";

import { useEffect, useState } from "react";
import api from "../../lib/api";

export default function WalletPage() {
  const [balance, setBalance] = useState(0);

  useEffect(() => {
    loadWallet();
  }, []);

  const loadWallet = async () => {
    const res = await api.get("/wallet");
    setBalance(res.data.balance);
  };

  return (
    <div style={{ padding: "40px" }}>
      <h1>Wallet</h1>
      <h2>Balance: ₹{balance}</h2>
    </div>
  );
}