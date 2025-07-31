document.addEventListener("DOMContentLoaded", () => {
  // PDF upload
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
      body: formData,
    });

    const result = await res.json();
    if (res.ok) {
      alert("PDF uploaded successfully.");
    } else {
      alert("Upload failed: " + result.detail);
    }
  };

  // Chat with PDF
  document.getElementById("chatForm").onsubmit = async (e) => {
    e.preventDefault();
    const message = document.getElementById("query").value;
    const res = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    document.getElementById("response").innerText = "AI: " + data.response;
  };
});
