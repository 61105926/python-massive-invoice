$(document).ready(() => {
    // Connect to Socket.IO server with explicit URL
    const socketUrl = window.location.protocol + "//" + window.location.hostname + ":" + window.location.port
    const socket = io.connect(socketUrl)
  
    let isProcessing = false
    const logEntries = []
    const maxLogEntries = 50
  
    // Add log entry function
    function addLogEntry(message, type = "info") {
      const timestamp = new Date().toLocaleTimeString()
      const entry = `<div class="log-entry ${type}">[${timestamp}] ${message}</div>`
  
      logEntries.push(entry)
      if (logEntries.length > maxLogEntries) {
        logEntries.shift()
      }
  
      $("#log-entries").html(logEntries.join(""))
      $(".log-container").scrollTop($(".log-container")[0].scrollHeight)
    }
  
    // Socket.IO connection events
    socket.on("connect", () => {
      addLogEntry("Conectado al servidor", "success")
      console.log("Socket.IO connected")
    })
  
    socket.on("disconnect", () => {
      addLogEntry("Desconectado del servidor", "error")
      console.log("Socket.IO disconnected")
    })
  
    socket.on("connect_error", (error) => {
      addLogEntry("Error de conexión: " + error, "error")
      console.error("Socket.IO connection error:", error)
    })
  
    // Handle form submission
    $("#upload-form").submit((e) => {
      e.preventDefault()
  
      if (isProcessing) {
        alert("Ya hay un proceso en ejecución. Por favor espere.")
        return
      }
  
      const excelFile = $("#excel")[0].files[0]
      if (!excelFile) {
        alert("Por favor, selecciona un archivo Excel.")
        return
      }
  
      // Reset UI
      isProcessing = true
      $("#submit-btn")
        .prop("disabled", true)
        .html('<span class="spinner-border" role="status" aria-hidden="true"></span> Procesando...')
      $("#progress-bar").css("width", "0%").text("0%").attr("aria-valuenow", 0)
      $("#progress-text").text("Iniciando proceso...")
      $(".progress-container").removeClass("success error").addClass("active")
      $("#download-btn").hide()
      logEntries.length = 0
      $("#log-entries").empty()
  
      addLogEntry("Subiendo archivo Excel...", "info")
  
      const formData = new FormData()
      formData.append("excel", excelFile)
  
      $.ajax({
        url: "/upload",
        type: "POST",
        data: formData,
        contentType: false,
        processData: false,
        success: (response) => {
          addLogEntry("Archivo subido correctamente. Iniciando descarga de facturas...", "success")
        },
        error: (xhr) => {
          isProcessing = false
          $("#submit-btn").prop("disabled", false).html('<i class="fas fa-download me-2"></i> Iniciar Descarga')
          $(".progress-container").removeClass("active").addClass("error")
  
          const errorMsg = xhr.responseText || "Error desconocido al iniciar la descarga."
          $("#progress-text").text("Error: " + errorMsg)
          addLogEntry("Error: " + errorMsg, "error")
        },
      })
    })
  
    // Handle progress updates
    socket.on("progress_update", (data) => {
      console.log("Progress update:", data)
  
      if (data.error) {
        addLogEntry(data.error, "error")
      }
  
      if (data.message) {
        addLogEntry(data.message)
      }
  
      if (data.total > 0) {
        const progressPercent = (data.current / data.total) * 100
        $("#progress-bar")
          .css("width", progressPercent + "%")
          .text(progressPercent.toFixed(0) + "%")
          .attr("aria-valuenow", progressPercent)
  
        if (data.message) {
          $("#progress-text").text(data.message)
        } else {
          $("#progress-text").text(`Procesando: ${data.current}/${data.total} (${progressPercent.toFixed(0)}%)`)
        }
      }
  
      // Check if download is complete or available
      if (data.download_url) {
        isProcessing = false
        $("#submit-btn").prop("disabled", false).html('<i class="fas fa-download me-2"></i> Iniciar Descarga')
  
        // Even if there were errors, if we have a download URL, consider it a partial success
        $(".progress-container").removeClass("active error").addClass("success")
  
        // Show download button
        $("#download-btn").show().attr("href", data.download_url)
  
        // If we have both errors and downloads, it's a partial success
        if (data.error) {
          addLogEntry(
            "Proceso completado con algunos errores. El archivo ZIP contiene las facturas que se pudieron descargar.",
            "warning",
          )
        } else {
          addLogEntry("Proceso completado. El archivo ZIP está listo para descargar.", "success")
        }
      }
  
      // If process is complete without a download URL
      if (data.current === data.total && data.total > 0 && !data.download_url) {
        isProcessing = false
        $("#submit-btn").prop("disabled", false).html('<i class="fas fa-download me-2"></i> Iniciar Descarga')
  
        if (data.error) {
          $(".progress-container").removeClass("active").addClass("error")
        } else {
          $(".progress-container").removeClass("active").addClass("success")
        }
      }
    })
  })
  