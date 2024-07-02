# academic-page-backend
academic-page-backend is used to retrieve publications and citation counts from ORCID and Crossref independently.

This backend is used in the academic-page repository https://github.com/justudin/academic-page.

## How to run it
Check that Python v3 is already installed. Then you can:

- Clone/download this repository (extracted it if needed)
- Go to `academic-page-backend` directory
- run `pip install -r requirements.txt`
- then run `gunicorn -b 127.0.0.1:9000 wsgi:app`
- Open your browser `127.0.0.1:9000`
- To get the ORCID publications list: 
`127.0.0.1:9000/orcid/0000-0002-5640-4413/works`
- Change the ORCID with your own ID.


# Debug mode in Window/CMD
- Go to `academic-page-backend` directory
- Activate your environtment
- set FLASK_ENV=development
- set FLASK_APP=app/main
- set MONGODB_URI=mongodb://localhost:27017
- set USR_CITED=usr (Change with your own)
- set PWD_CITED=pwd (Change with your own)
- flask run