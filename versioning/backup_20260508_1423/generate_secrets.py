import json

# Load your local service account file
with open('service_account.json', 'r') as f:
    creds = json.load(f)

# Use your spreadsheet URL
url = "https://docs.google.com/spreadsheets/d/1lKL7VkZoLxbrLbX2bVyF8wdb8bxXxBbJGgoQSg7OVUU/edit"

# Generate the TOML
print("\n--- COPY EVERYTHING BELOW THIS LINE ---\n")
print("[connections.gsheets]")
print(f'spreadsheet = "{url}"')
print('type = "service_account"')
print(f'project_id = "{creds["project_id"]}"')
print(f'private_key_id = "{creds["private_key_id"]}"')
print('private_key = """' + creds["private_key"] + '"""')
print(f'client_email = "{creds["client_email"]}"')
print(f'client_id = "{creds["client_id"]}"')
print(f'auth_uri = "{creds["auth_uri"]}"')
print(f'token_uri = "{creds["token_uri"]}"')
print(f'auth_provider_x509_cert_url = "{creds["auth_provider_x509_cert_url"]}"')
print(f'client_x509_cert_url = "{creds["client_x509_cert_url"]}"')
print('universe_domain = "googleapis.com"')
print("\n--- STOP COPYING ABOVE THIS LINE ---\n")
