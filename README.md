# discord-storage
 Using discord cdn as a cloud storage!

# Installing
 **Python 3.8 or higher is required**

 ## 1. Download the Project
 First, download the source code of the project. You can obtain the project's source code by:
 ```bash
 git clone https://github.com/watermelon1024/discord-storage.git
 cd discord-storage
 ```

 ## 2. Use a Virtual Environment (Optional but Recommended)
 Before installing the project, it's recommended to use a virtual environment to isolate the project's dependencies and prevent conflicts with dependencies of other projects.
 ### Using Python's Built-in Virtual Environment Module
 ```bash
 python -m venv venv
 ```
 ### Using a Third-Party Virtual Environment Management Tool
 ```bash
 pip install virtualenv

 virtualenv venv
 ```
 # Activate the virtual environment
 ```bash
 # Windows
 venv\Scripts\activate

 # Linux/macOS
 source venv/bin/activate
 ```

 ## 3. Set Up Environment Variables
 Rename the .env.example file to .env and fill in the required values for each environment variable according to your configuration.

 ### `.env.example`
 ```
 TOKEN=  # Discord Bot token
 CHANNEL=  # Storage channel ID (private channel recommended)
 SERVER_HOST=127.0.0.1  # Web server host
 SERVER_PORT=8000  # Web server port
 ```

 4. Install Dependencies
 Install the dependencies required for the project.
 ```bash
 pip install -r requirements.txt
 ```

 5. Run the Project
 Once the dependencies are installed and the environment variables are set up, you can run the project!
 ```bash
 # Run the project in the project directory
 python your_project.py
 ```
