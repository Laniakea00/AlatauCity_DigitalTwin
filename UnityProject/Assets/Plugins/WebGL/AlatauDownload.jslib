// The weekly report PDF of the construction monitoring: hands a byte array from C# to the browser as a file download.
mergeInto(LibraryManager.library, {
  AlatauDownloadFile: function (namePtr, dataPtr, length, mimePtr) {
    var name = UTF8ToString(namePtr);
    var mime = UTF8ToString(mimePtr) || "application/octet-stream";
    var bytes = HEAPU8.slice(dataPtr, dataPtr + length);
    var blob = new Blob([bytes], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = name; a.style.display = "none";
    document.body.appendChild(a); a.click();
    setTimeout(function () { document.body.removeChild(a); URL.revokeObjectURL(url); }, 1500);
  }
});
