const ASSISTANT_API_URL = "http://127.0.0.1:8000/api/chat";

async function askYoiAssistant(message) {
  const response = await fetch(ASSISTANT_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ message })
  });

  const payload = await response.json();

  if (!response.ok) {
    throw new Error(
      payload.detail || "The assistant request failed."
    );
  }

  console.log("Tool trace:", payload.tool_trace);
  console.log("Usage:", payload.usage);
  console.log(
    "Estimated paid cost:",
    payload.estimated_paid_cost_usd
  );

  return payload.answer;
}
