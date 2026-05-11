import libsql_client
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

def export_turso_to_csv(output_file="database_export.csv"):
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    
    if not url or not token:
        print("Error: TURSO_DATABASE_URL or TURSO_AUTH_TOKEN not found in .env file.")
        return

    print(f"Connecting to Turso at {url}...")
    try:
        client = libsql_client.create_client_sync(url=url, auth_token=token)
        result = client.execute("SELECT * FROM media_references")
        
        # Convert to DataFrame
        df = pd.DataFrame(result.rows, columns=result.columns)
        
        if df.empty:
            print("The database is currently empty. No data to export.")
        else:
            # Sort by season and episode if possible
            if 'season' in df.columns and 'episode_number' in df.columns:
                def extract_num(val):
                    import re
                    if not val or val == "": return 0
                    match = re.search(r'(\d+)', str(val))
                    return float(match.group(1)) if match else 0
                
                df['s_sort'] = df['season'].apply(extract_num)
                df['e_sort'] = df['episode_number'].apply(extract_num)
                df = df.sort_values(by=['s_sort', 'e_sort'])
                df = df.drop(columns=['s_sort', 'e_sort'])

            df.to_csv(output_file, index=False)
            print(f"Successfully exported {len(df)} records to {output_file}")
        
        client.close()
    except Exception as e:
        print(f"Failed to export data: {e}")

if __name__ == "__main__":
    export_turso_to_csv()
