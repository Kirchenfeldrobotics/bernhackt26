"use client";

import { useState } from "react";
import type React from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function CompanyFormPage() {
  const [name, setName] = useState("");
  const [details, setDetails] = useState("");
  const [status, setStatus] = useState("");

  function handleNameChange(event: React.ChangeEvent<HTMLInputElement>) {
    setName(event.target.value);
  }

  function handleDetailsChange(event: React.ChangeEvent<HTMLTextAreaElement>) {
    setDetails(event.target.value);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("Enviando...");

    try {
      const response = await fetch(`${API_URL}/companies`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name,
          details,
          category: null,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setStatus(`Enviado com sucesso! ${JSON.stringify(data)}`);
      } else {
        setStatus(`Erro: ${JSON.stringify(data)}`);
      }
    } catch (error) {
      setStatus(`Erro de rede: ${String(error)}`);
    }
  }

  return (
    <div>
      <h1>Formulario de teste - Empresa</h1>
      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="name">Nome da empresa</label>
          <br />
          <input
            id="name"
            type="text"
            value={name}
            onChange={handleNameChange}
            required
          />
        </div>
        <div>
          <label htmlFor="details">Detalhes de como ela funciona</label>
          <br />
          <textarea
            id="details"
            value={details}
            onChange={handleDetailsChange}
          />
        </div>
        <button type="submit">Enviar</button>
      </form>
      <p>{status}</p>
    </div>
  );
}
