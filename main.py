from flask import Flask, request, jsonify, send_file
import zipfile
import requests
import io
import os
from datetime import datetime
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


@app.route('/', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok",
        "service": "ZIP Archive Service",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/create-zip', methods=['POST'])
def create_zip():
    try:
        data = request.get_json()

        # Проверяем входные данные
        if not data or 'files' not in data:
            return jsonify({
                "error": "Missing 'files' array in request"
            }), 400

        files = data['files']
        archive_name = data.get('name', 'archive.zip')
        apartment_id = data.get('apartment_id', 'unknown')

        logging.info(f"Creating archive '{archive_name}' with {len(files)} files")

        # Создаем ZIP архив в памяти
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for i, file_info in enumerate(files):
                try:
                    file_url = file_info.get('url')
                    filename = file_info.get('name', f'file_{i + 1}.jpg')

                    if not file_url:
                        logging.warning(f"Skipping file {i + 1}: no URL provided")
                        continue

                    # Скачиваем файл
                    logging.info(f"Downloading: {filename}")
                    response = requests.get(file_url, timeout=30, stream=True)

                    if response.status_code == 200:
                        # Добавляем файл в архив
                        zip_file.writestr(filename, response.content)
                        logging.info(f"Added: {filename}")
                    else:
                        logging.warning(f"Failed to download {filename}: HTTP {response.status_code}")

                except Exception as e:
                    logging.error(f"Error processing {filename}: {e}")
                    continue

        # Получаем готовый архив
        zip_buffer.seek(0)
        archive_data = zip_buffer.read()

        logging.info(f"Archive created: {len(archive_data)} bytes")

        # Пытаемся загрузить на file.io
        try:
            logging.info("Uploading to file.io...")

            files_payload = {
                'file': (archive_name, io.BytesIO(archive_data), 'application/zip')
            }

            fileio_response = requests.post('https://file.io', files=files_payload, timeout=60)

            logging.info(f"file.io response status: {fileio_response.status_code}")
            logging.info(f"file.io response text (first 200 chars): {fileio_response.text[:200]}")

            # Пытаемся распарсить JSON
            try:
                fileio_data = fileio_response.json()

                if fileio_data.get('success'):
                    logging.info(f"file.io upload successful: {fileio_data.get('link')}")
                    return jsonify({
                        "success": True,
                        "download_url": fileio_data['link'],
                        "file_key": fileio_data.get('key', ''),
                        "archive_name": archive_name,
                        "files_count": len(files),
                        "archive_size": len(archive_data),
                        "apartment_id": apartment_id,
                        "expiry": fileio_data.get('expiry', '14 days')
                    })
                else:
                    logging.warning(f"file.io returned success=false: {fileio_data}")

            except Exception as json_error:
                logging.error(f"Failed to parse file.io JSON response: {json_error}")
                logging.error(f"Full file.io response: {fileio_response.text}")

        except Exception as upload_error:
            logging.error(f"Error uploading to file.io: {upload_error}")

        # Если file.io не сработал, возвращаем архив напрямую
        logging.info("file.io failed, returning archive directly")
        return send_file(
            io.BytesIO(archive_data),
            as_attachment=True,
            download_name=archive_name,
            mimetype='application/zip'
        )

    except Exception as e:
        logging.error(f"Error creating archive: {e}")
        return jsonify({
            "error": "Failed to create archive",
            "details": str(e)
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
