document.addEventListener("DOMContentLoaded", () => {
  const token = getCookie("access_token");
  if (!token) {
    alert("Please log in first.");
    window.location.href = "/auth/login";
    return;
  }

  // Upload PDF
  document.getElementById("uploadForm").onsubmit = async (e) => {
    e.preventDefault();
    const file = document.querySelector('input[name="file"]').files[0];
    if (!file || file.type !== "application/pdf") {
      alert("Please upload a valid PDF.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("/upload", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    });

    const result = await res.json();
    if (res.ok) {
      alert("PDF uploaded successfully.");
    } else {
      alert("Upload failed: " + result.detail);
    }
  };

  // Chat
  document.getElementById("chatForm").onsubmit = async (e) => {
    e.preventDefault();
    const message = document.getElementById("query").value;
    const res = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    document.getElementById("response").innerText = "AI: " + data.response;
  };
});

// Utility to read cookies
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  return parts.length === 2 ? parts.pop().split(";").shift() : null;
}
