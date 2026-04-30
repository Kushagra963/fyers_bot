"""
Fyers Authentication Module
Handles login, TOTP generation, and token management
Uses environment variables from .env file
"""

import os
import sys
import traceback

# Check for required packages
try:
    import pyotp
except ImportError:
    print("ERROR: pyotp not installed. Run: pip install pyotp")
    sys.exit(1)

try:
    from fyers_apiv3 import fyersModel
except ImportError:
    print("ERROR: fyers-apiv3 not installed. Run: pip install fyers-apiv3")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

import logging

# Load environment variables
print("Loading environment variables from .env file...")
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FyersAuth:
    """Handle Fyers authentication and token management"""
    
    def __init__(self):
        print("\n" + "="*80)
        print("Initializing Fyers Authentication")
        print("="*80)
        
        # Load credentials from environment variables
        self.app_id = os.getenv('FYERS_APP_ID')
        self.secret_key = os.getenv('FYERS_SECRET_KEY')
        self.redirect_uri = os.getenv('FYERS_REDIRECT_URI')
        self.totp_key = os.getenv('FYERS_TOTP_SECRET')
        self.pin = os.getenv('FYERS_PIN')
        
        # Debug output (masked)
        print(f"App ID: {self.app_id[:10] + '...' if self.app_id else 'NOT SET'}")
        print(f"Secret Key: {'SET' if self.secret_key else 'NOT SET'}")
        print(f"Redirect URI: {self.redirect_uri if self.redirect_uri else 'NOT SET'}")
        print(f"PIN: {'SET' if self.pin else 'NOT SET'}")
        print(f"TOTP Key: {'SET' if self.totp_key else 'NOT SET'}")
        
        # Validate required credentials
        missing = []
        if not self.app_id:
            missing.append("FYERS_APP_ID")
        if not self.secret_key:
            missing.append("FYERS_SECRET_KEY")
        if not self.redirect_uri:
            missing.append("FYERS_REDIRECT_URI")
        if not self.totp_key:
            missing.append("FYERS_TOTP_SECRET")
        if not self.pin:
            missing.append("FYERS_PIN")
        
        if missing:
            print("\n❌ ERROR: Missing required environment variables in .env file:")
            for var in missing:
                print(f"   - {var}")
            print("\nPlease update your .env file with all required credentials.")
            raise ValueError(f"Missing required credentials: {', '.join(missing)}")
        
        print("✓ All credentials loaded successfully")
        
        self.client_id = self.app_id  # For API v3, client_id is same as app_id
        
        self.access_token = None
        self.fyers = None
        print("="*80 + "\n")
        
    def generate_totp(self):
        """Generate current TOTP code"""
        try:
            totp = pyotp.TOTP(self.totp_key)
            code = totp.now()
            logger.info(f"Generated TOTP code: {code}")
            return code
        except Exception as e:
            logger.error(f"Error generating TOTP: {e}")
            raise
    
    def get_auth_code(self):
        """
        Get authorization code through Fyers login flow
        This requires manual browser interaction for the first time
        """
        try:
            # Create session model for login
            session = fyersModel.SessionModel(
                client_id=self.client_id,
                secret_key=self.secret_key,
                redirect_uri=self.redirect_uri,
                response_type="code",
                grant_type="authorization_code"
            )
            
            # Generate auth code URL
            auth_url = session.generate_authcode()
            logger.info(f"Authorization URL: {auth_url}")
            
            print("\n" + "="*80)
            print("FYERS AUTHENTICATION REQUIRED")
            print("="*80)
            print(f"\n1. Open this URL in your browser:\n   {auth_url}")
            print(f"\n2. Login with your credentials")
            print(f"   - PIN: {self.pin}")
            print(f"   - TOTP: {self.generate_totp()}")
            print(f"\n3. After login, you'll be redirected to: {self.redirect_uri}")
            print(f"4. Copy the FULL redirect URL from browser address bar")
            print("="*80 + "\n")
            
            # Get redirect URL from user
            redirect_response = input("Paste the redirect URL here: ").strip()
            
            # Extract auth code from redirect URL
            auth_code = redirect_response.split("auth_code=")[1].split("&")[0]
            logger.info(f"Extracted auth code: {auth_code[:10]}...")
            
            return auth_code
            
        except Exception as e:
            logger.error(f"Error getting auth code: {e}")
            raise
    
    def generate_access_token(self, auth_code=None):
        """
        Generate access token from auth code
        """
        try:
            if not auth_code:
                auth_code = self.get_auth_code()
            
            # Create session for token generation
            session = fyersModel.SessionModel(
                client_id=self.client_id,
                secret_key=self.secret_key,
                redirect_uri=self.redirect_uri,
                response_type="code",
                grant_type="authorization_code"
            )
            
            # Set auth code
            session.set_token(auth_code)
            
            # Generate access token
            response = session.generate_token()
            
            if response['code'] == 200:
                self.access_token = response['access_token']
                logger.info("Access token generated successfully")
                logger.info(f"Token: {self.access_token[:20]}...")
                
                # Initialize Fyers model with access token
                self.initialize_fyers()
                
                return self.access_token
            else:
                logger.error(f"Token generation failed: {response}")
                raise Exception(f"Token generation failed: {response['message']}")
                
        except Exception as e:
            logger.error(f"Error generating access token: {e}")
            raise
    
    def initialize_fyers(self):
        """Initialize Fyers model with access token"""
        try:
            if not self.access_token:
                raise Exception("No access token available. Please authenticate first.")
            
            self.fyers = fyersModel.FyersModel(
                client_id=self.client_id,
                is_async=False,
                token=self.access_token,
                log_path=""
            )
            
            logger.info("Fyers model initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Fyers: {e}")
            raise
    
    def get_profile(self):
        """Get user profile to verify authentication"""
        try:
            if not self.fyers:
                raise Exception("Fyers not initialized. Please authenticate first.")
            
            response = self.fyers.get_profile()
            
            if response['code'] == 200:
                logger.info(f"Profile retrieved: {response['data']['name']}")
                return response['data']
            else:
                logger.error(f"Profile retrieval failed: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting profile: {e}")
            raise
    
    def is_authenticated(self):
        """Check if currently authenticated"""
        try:
            if not self.fyers or not self.access_token:
                return False
            
            # Try to get profile to verify token is valid
            profile = self.get_profile()
            return profile is not None
            
        except:
            return False
    
    def login(self):
        """
        Complete login flow
        Returns True if successful, False otherwise
        """
        try:
            logger.info("Starting Fyers login flow...")
            
            # Check if already authenticated
            if self.is_authenticated():
                logger.info("Already authenticated")
                return True
            
            # Get auth code and generate token
            auth_code = self.get_auth_code()
            self.generate_access_token(auth_code)
            
            # Verify authentication
            if self.is_authenticated():
                logger.info("Login successful!")
                profile = self.get_profile()
                print(f"\n✓ Logged in as: {profile['name']}")
                print(f"✓ Client ID: {profile['fy_id']}")
                print(f"✓ Email: {profile['email_id']}")
                return True
            else:
                logger.error("Login verification failed")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False


def main():
    """Test authentication"""
    try:
        print("\n" + "="*80)
        print("FYERS AUTHENTICATION TEST")
        print("="*80 + "\n")
        
        # Initialize auth
        auth = FyersAuth()
        
        # Test TOTP generation
        print("Testing TOTP generation...")
        totp = auth.generate_totp()
        print(f"✓ Current TOTP: {totp}")
        print(f"  (This code changes every 30 seconds)\n")
        
        # Test login
        if auth.login():
            print("\n" + "="*80)
            print("✅ AUTHENTICATION SUCCESSFUL")
            print("="*80)
            print(f"\nAccess Token: {auth.access_token[:30]}...")
            print("\n✓ You can now use this token for trading!")
            print("="*80 + "\n")
        else:
            print("\n" + "="*80)
            print("❌ AUTHENTICATION FAILED")
            print("="*80 + "\n")
            
    except Exception as e:
        print("\n" + "="*80)
        print("❌ ERROR OCCURRED")
        print("="*80)
        print(f"\nError: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        print("="*80 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()