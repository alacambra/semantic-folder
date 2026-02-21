"""Azure Functions V2 entry point — registers blueprints from src/."""

import os
import sys

# Add src/ to Python path so that Azure Functions runtime can resolve
# the semantic_folder package from the src/ layout.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import azure.functions as func

from semantic_folder.functions.http_trigger import bp as http_bp
from semantic_folder.functions.timer_trigger import bp as timer_bp

app = func.FunctionApp()
app.register_blueprint(timer_bp)
app.register_blueprint(http_bp)
