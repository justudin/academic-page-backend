from flask import Flask, request, jsonify, make_response, render_template
import requests as req
import datetime
from functools import reduce
import requests_cache
from flask_cors import CORS
from datetime import date

# scopus API client
from elsapy.elsclient import ElsClient
from elsapy.elsprofile import ElsAuthor, ElsAffil
from elsapy.elsdoc import FullDoc, AbsDoc
from elsapy.elssearch import ElsSearch
import json

## Load configuration
con_file = open(".scopus-config.json")
config = json.load(con_file)
con_file.close()

## Initialize client
client = ElsClient(config['apikey'])


app = Flask(__name__)
HEADERS = {'Accept': 'application/vnd.orcid+json', 'User-Agent': 'Academic Page/0.1.1 (https://github.com/justudin/academic-page; mailto:just.udin@yahoo.com) to retrieve citation counts'}
requests_cache.install_cache('orcidcrossref_cache', backend='sqlite', expire_after=86400)
CORS(app)

@app.route("/hello")
def hello():
    data = {
    'status':'ok',
    'data':'Hello There - WebAPIs!'
    }
    return data

@app.route("/version")
def version_api():
    data = {
    'status':'ok',
    'data':'as of 2022-07-01'
    }
    return data

@app.route("/orcid/<orcid_id>/works")
def orcid_data_part(orcid_id):
    #print("orcid_data_part")
    #update = request.args.get('update')
    if orcid_id:
        key = {'orcid': orcid_id}
        data_mongodb = get_orcid_crossref(orcid_id)
        return jsonify(data_mongodb)
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)

@app.route("/orcid/<orcid_id>/works/html")
def orcid_data_part_html(orcid_id):
    #print("orcid_data_part")
    #update = request.args.get('update')
    if orcid_id:
        key = {'orcid': orcid_id}
        data_mongodb = get_orcid_crossref(orcid_id)
        return render_template('works.html', data=data_mongodb)
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)

@app.route("/orcid/<orcid_id>/reviews")
def orcid_data_part_reviews(orcid_id):
    #print("orcid_data_part")
    #update = request.args.get('update')
    if orcid_id:
        key = {'orcid': orcid_id}
        data_mongodb = get_orcid_reviews(orcid_id)
        return jsonify(data_mongodb)
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)


@app.route("/scopus/<scopus_id>/summary")
def scopus_data_summary(scopus_id):
    #print("orcid_data_part")
    #update = request.args.get('update')
    if scopus_id:
        key = {'orcid': scopus_id}
        data_mongodb = get_scopus_summary(scopus_id)
        return jsonify(data_mongodb)
    else:
        message = jsonify(message='Please provide the SCOPUS ID')
        return make_response(message, 400)

def get_scopus_summary(scopus_id):
    today = date.today()
    todaydate = today.strftime("%d/%m/%Y")
    scopus_data = ElsAuthor(uri = 'https://api.elsevier.com/content/author/author_id/'+str(scopus_id))
    data_mongodb = {}
    if scopus_data.read_metrics(client):
        data_mongodb['scopus_id'] = scopus_id
        data_mongodb['total_citations'] = scopus_data.data['coredata']['citation-count']
        data_mongodb['total_papers'] = scopus_data.data['coredata']['document-count']
        data_mongodb['hindex'] = scopus_data.data['h-index']
        data_mongodb['updated'] = todaydate
        
    else:
        print ("Read author failed.")
    return data_mongodb


@app.route("/")
def welcome():
    return "Welcome abroad!"

def get_orcid_crossref(orcid_id):
    today = date.today()
    todaydate = today.strftime("%d/%m/%Y")
    headers_config = {'User-Agent': 'Academic Page/0.1.1 (https://github.com/justudin/academic-page; mailto:just.udin@yahoo.com) to retrieve citation counts'}
    URL_ORCID = "https://pub.orcid.org/v3.0/"+str(orcid_id)+"/works"
    r = req.get(URL_ORCID, headers=HEADERS)
    orcid_dt = r.json()
    data_mongodb = {}
    key = {'orcid': orcid_id}
    if len(orcid_dt["group"])>0:
        data_dois = []
        for dt in orcid_dt["group"]:
            dois = dt["external-ids"]["external-id"]
            for d in dois:
                if d['external-id-type'] == "doi":
                    doi = d['external-id-value']
                    data_dois.append(doi)
        #print(data_dois)
        data_all = []
        citations = []
        if len(data_dois)>0:
            for doi in data_dois:
                URL_CROSSREF = "https://api.crossref.org/works/"+str(doi)
                cross = req.get(URL_CROSSREF, headers=headers_config)
                cross_dt = cross.json()
                citation = cross_dt["message"]["is-referenced-by-count"]
                citations.append(citation)
                title = cross_dt["message"]["title"][0]
                typepaper = cross_dt["message"]["type"]
                created = cross_dt["message"]["created"]["timestamp"]
                year = cross_dt["message"]["created"]["date-parts"][0][0]
                data_all.append({'title':title, 'doi': doi, 'type':typepaper, 'year':year, 'created':created,'citation':citation})
            data_all.sort(key=lambda x: x.get('year'), reverse=True)
        hIndexScore = hIndex(citations)

        data_mongodb = {'orcid':orcid_id, 'data':data_all, 'total_papers': len(citations), 'total_citations': sum(citations), 'hindex': hIndexScore, 'updated': todaydate}

    return data_mongodb

def get_orcid_reviews(orcid_id):
    today = date.today()
    todaydate = today.strftime("%d/%m/%Y")
    headers_config = {'User-Agent': 'Academic Page/0.1.1 (https://github.com/justudin/academic-page; mailto:just.udin@yahoo.com) to retrieve citation counts'}
    URL_ORCID = "https://orcid.org/"+str(orcid_id)+"/peer-reviews-minimized.json?sortAsc=true"
    r = req.get(URL_ORCID, headers=HEADERS)
    orcid_dt = r.json()
    data_mongodb = {}
    key = {'orcid': orcid_id}
    total_outlet = len(orcid_dt)
    total_review = 0
    if total_outlet>0:
        data_all = []
        for dt in orcid_dt:
            total_review += dt["duplicated"]
            data_all.append({'outlet':dt["name"], 'issn': dt["groupIdValue"].rsplit(':', 1)[-1], 'reviews':dt["duplicated"]})
        data_all.sort(key=lambda x: x.get('reviews'), reverse=True)
        data_mongodb = {'orcid':orcid_id, 'data':data_all, 'total_reviews': total_review, 'total_outlets': total_outlet, 'updated': todaydate}
    return data_mongodb

def get_reviews(data):
    return data.get('reviews')

@app.errorhandler(404)
def page_not_found(e):
    message = jsonify(error=True, message='The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.')
    return make_response(message, 404)

def deep_get(dictionary, keys, default=None):
    return reduce(lambda d, key: d.get(key, default) if isinstance(d, dict) else default, keys.split("."), dictionary)

def hIndex(citations):
    return sum(x >= i + 1 for i, x in enumerate(sorted(list(citations), reverse=True)))

def get_data_mongodb(data):
    del data['_id']
    data["info"] = "data is not fresh"
    #data['_id'] = str(data['_id'])
    return data
