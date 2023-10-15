function initializeTabCapture(textareaId) {
  var textarea = document.getElementById(textareaId);

  if (textarea) {
    textarea.addEventListener('keydown', function(e) {
      if (e.key === 'Tab') {
        e.preventDefault(); // Prevent the default tab behavior
        var start = this.selectionStart;
        var end = this.selectionEnd;

        // Insert a tab character at the current cursor position
        this.value = this.value.substring(0, start) + '\t' + this.value.substring(end);

        // Set the cursor position after the inserted tab
        this.selectionStart = this.selectionEnd = start + 1;
      }
    });
  }
}
