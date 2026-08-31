def upload_to_drive(file_path):
    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")
    
    print(f"Debug - Folder ID length: {len(folder_id) if folder_id else 'MISSING'}")
    
    if not creds_json or not folder_id:
        print("Error: Missing GDRIVE_CREDENTIALS or GDRIVE_FOLDER_ID environment variables!")
        return
        
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(
        creds_dict, 
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    
    service = build("drive", "v3", credentials=creds)
    file_name = "Lahore_Broiler_And_DOC_90Days.json"

    # Search if file already exists in the folder
    query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
    results = service.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    files = results.get("files", [])

    media = MediaFileUpload(file_path, mimetype="application/json")

    if files:
        service.files().update(fileId=files[0]["id"], media_body=media, supportsAllDrives=True).execute()
        print("File updated on Drive!")
    else:
        file_metadata = {"name": file_name, "parents": [folder_id]}
        service.files().create(body=file_metadata, media_body=media, fields="id", supportsAllDrives=True).execute()
        print("File created on Drive!")
