def download_file(url, save_path):
    try:
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        csv_link = soup.select_one('a[href$=".csv"]')['href']
        full_csv_link = urljoin(url, csv_link)

        with requests.get(full_csv_link, stream=True) as csv_response:
            csv_response.raise_for_status()
            with open(save_path, 'wb') as file:
                for chunk in csv_response.iter_content(chunk_size=8192):
                    file.write(chunk)
        
        print(f"CSV file downloaded successfully and saved at {save_path}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to download the file. Error: {e}")