import tempfile

from gui import app_paths

# A modulok importáláskor az app mappába írnak: a tesztek ne a repóba írjanak
app_paths.init(tempfile.mkdtemp(prefix="gamebooster-test-"))
