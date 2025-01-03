from flask import Flask, request, jsonify, make_response, render_template, redirect
import string, random
from werkzeug.exceptions import HTTPException
import requests
import datetime
from datetime import datetime, timedelta
from functools import reduce
import requests_cache
from flask_cors import CORS
from datetime import date
from time import time
import json
from itertools import accumulate
import xmltodict
import os
import hashlib
from requests_cache import CachedSession, SQLiteCache
from collections import defaultdict
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from scholarly import scholarly, ProxyGenerator
pg = ProxyGenerator()
scholarly.use_proxy(pg)

'''
import logging
logging.basicConfig(level='DEBUG')
'''

USR_CITED = os.getenv('USR_CITED')
PWD_CITED = os.getenv('PWD_CITED')
MONGODB_URI = os.getenv('MONGODB_URI')

if MONGODB_URI is None:
    mongo_client = MongoClient("mongodb://localhost:27017")
else:
    mongo_client = MongoClient(MONGODB_URI+'/?retryWrites=true&w=majority&appName=AtlasCluster', server_api=ServerApi('1'))

db = mongo_client["academic-backend"]

app = Flask(__name__)
HEADERS = {'Accept': 'application/vnd.orcid+json', 'User-Agent': 'Academic Page/0.1.1 (https://github.com/justudin/academic-page; mailto:just.udin@yahoo.com) to retrieve citation counts'}
backend = SQLiteCache('orcidcrossref_cache')
requests_cache.install_cache(backend=backend, expire_after=86400)

CORS(app)

# Generate a random short link
def generate_short_link():
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(6))

@app.route('/shorten', methods=['POST'])
def shorten_url():
    """
    Endpoint to shorten a URL.
    Expects JSON input: {"url": "http://example.com", "short_link":"custom"}
    """
    data = request.json
    original_url = data.get("url")
    short_link = data.get("short_link")
    
    if not original_url:
        return jsonify({"error": "URL is required"}), 400

    # Check if the URL is already in the database
    existing_entry = db.urls.find_one({"original_url": original_url})
    if existing_entry:
        short_link = existing_entry["short_link"]
    else:
        if not short_link:
            # Generate a new short link
            short_link = generate_short_link()
            while db.urls.find_one({"short_link": short_link}):  # Ensure uniqueness
                short_link = generate_short_link()

        # Save to the database
        db.urls.insert_one({
            "original_url": original_url,
            "short_link": short_link
        })
    
    return jsonify({
        "short_link": BASE_URL + short_link,
        "original_url": original_url
    })

@app.route('/<short_link>')
def redirect_url(short_link):
    """
    Redirect to the original URL based on the short link.
    """
    # Lookup the short link in the database
    entry = db.urls.find_one({"short_link": short_link})
    if entry:
        return redirect(entry["original_url"])
    return jsonify({"error": "Not found"}), 404


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
    'data':'developed as of 2024-07-02'
    }
    return data

@app.route("/orcid/<orcid_id>/works.json")
def orcid_data_part(orcid_id):
    db_request = request.args.get('update')
    db_request = True if db_request is None else False
    if orcid_id:
        key = {'orcid': orcid_id}
        data_mongodb = get_orcid_crossref(orcid_id, db_request)
        return jsonify(data_mongodb)
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)

@app.route("/orcid/<orcid_id>/works.html")
def orcid_data_part_html(orcid_id):
    db_request = request.args.get('update')
    db_request = True if db_request is None else False
    if orcid_id:
        key = {'orcid': orcid_id}
        data_mongodb = get_orcid_crossref(orcid_id, db_request)
        return render_template('works.html', data=data_mongodb)
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)

@app.route("/orcid/<orcid_id>/works.chart")
def orcid_data_part_chart(orcid_id):
    db_request = request.args.get('update')
    db_request = True if db_request is None else False
    if orcid_id:
        key = {'orcid': orcid_id}
        data_mongodb = get_orcid_crossref(orcid_id, db_request)
        labels = list(data_mongodb["yearly_publications"].keys())
        labels_line = sorted(labels, key=int)
        values_line = [data_mongodb["yearly_publications"][year] for year in labels_line]
        accumulated_values = list(accumulate(values_line))
        PastY = 3
        labels_pie = list(data_mongodb["category_publications"].keys())
        values_pie = list(data_mongodb["category_publications"].values())
        citations_labels = list(data_mongodb["yc_citations"].keys())
        citations_labels_line = sorted(citations_labels, key=int)
        citations_values_line = [data_mongodb["yc_citations"][year] for year in citations_labels_line]
        citations_accumulated_values = list(accumulate(citations_values_line))
        accumulated_values = list(accumulate(values_line))

        return render_template('chart.html', citations_labels=citations_labels_line, citations_values_line=citations_values_line, citations_accumulated_values=citations_accumulated_values, accumulated_values=accumulated_values[-PastY:], PastY=PastY, labels_line=labels_line[-PastY:], values_line=values_line[-PastY:], labels_pie=labels_pie, values_pie=values_pie)
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)


@app.route("/orcid/<orcid_id>/reviews.json")
def orcid_data_part_reviews(orcid_id):
    db_request = request.args.get('update')
    db_request = True if db_request is None else False
    if orcid_id:
        key = {'orcid': orcid_id}
        data_mongodb = get_orcid_reviews(orcid_id, db_request)
        return jsonify(data_mongodb)
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)

@app.route("/orcid/<orcid_id>/googlescholar.json")
def orcid_googlescholar(orcid_id):
    db_request = request.args.get('update')
    db_request = True if db_request is None else False
    if orcid_id:
        data = get_orcid_googlescholar(orcid_id, db_request)
        return jsonify(data)
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)

@app.route("/orcid/<orcid_id>/googlescholar.html")
def orcid_googlescholar_html(orcid_id):
    db_request = request.args.get('update')
    db_request = True if db_request is None else False
    if orcid_id:
        key = {'orcid': orcid_id}
        data_mongodb = get_orcid_googlescholar(orcid_id, db_request)
        return render_template('gs_works.html', data=data_mongodb)
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)

@app.route("/orcid/<orcid_id>/googlescholar.chart")
def orcid_googlescholar_chart(orcid_id):
    db_request = request.args.get('update')
    db_request = True if db_request is None else False
    if orcid_id:
        key = {'orcid': orcid_id}
        data_mongodb = get_orcid_googlescholar(orcid_id, db_request)
        # Extract keys as labels and values as data
        labels = list(data_mongodb["yearly_publications"].keys())
        labels_line = sorted(labels, key=int)
        values_line = [data_mongodb["yearly_publications"][year] for year in labels_line]
        accumulated_values = list(accumulate(values_line))
        PastY = 3
        citations_labels = list(data_mongodb["yc_citations"].keys())
        citations_labels_line = sorted(citations_labels, key=int)
        citations_values_line = [data_mongodb["yc_citations"][year] for year in citations_labels_line]
        citations_accumulated_values = list(accumulate(citations_values_line))
        accumulated_values = list(accumulate(values_line))
        return render_template('gs_chart.html', gs_id=data_mongodb['gs_id'], updated=data_mongodb['updated'], citations_labels=citations_labels_line, citations_values_line=citations_values_line, citations_accumulated_values=citations_accumulated_values, accumulated_values=accumulated_values[-PastY:], PastY=PastY, labels_line=labels_line[-PastY:], values_line=values_line[-PastY:])
    else:
        message = jsonify(message='Please provide the ORCID ID')
        return make_response(message, 400)

@app.route("/citations")
def googlescholar_citations():
    user = request.args.get('user')
    op = request.args.get('op')
    db_request = request.args.get('update')
    db_request = True if db_request is None else False
    if user:
        data_mongodb = get_googlescholar_data(user, db_request)
        if op=='json':
            return jsonify(data_mongodb)
        elif op=='chart':
            # Extract keys as labels and values as data
            labels = list(data_mongodb["yearly_publications"].keys())
            labels_line = sorted(labels, key=int)
            values_line = [data_mongodb["yearly_publications"][year] for year in labels_line]
            accumulated_values = list(accumulate(values_line))
            PastY = 3
            citations_labels = list(data_mongodb["yc_citations"].keys())
            citations_labels_line = sorted(citations_labels, key=int)
            citations_values_line = [data_mongodb["yc_citations"][year] for year in citations_labels_line]
            citations_accumulated_values = list(accumulate(citations_values_line))
            accumulated_values = list(accumulate(values_line))
            return render_template('gs_chart.html', gs_id=data_mongodb['gs_id'], updated=data_mongodb['updated'], citations_labels=citations_labels_line, citations_values_line=citations_values_line, citations_accumulated_values=citations_accumulated_values, accumulated_values=accumulated_values[-PastY:], PastY=PastY, labels_line=labels_line[-PastY:], values_line=values_line[-PastY:])
        elif op=='html':
            return render_template('gs_works.html', data=data_mongodb)
        else:
            return jsonify(data_mongodb)
    else:
        message = jsonify(message='Please provide the GoogleScholar user id')
        return make_response(message, 400)

@app.route("/")
def welcome():
    return "Welcome abroad!"

def get_googlescholar_data(user, db_request=False):
    # check if data already exist
    data = db.orcid_googlescholar.find_one({'user': user}, {'_id': False})
    if(data and db_request):
        return data
    else:
        today = datetime.today()
        todaydate = today.strftime("%d/%m/%Y %H:%M:%S")
        # record start time
        time_start = time()
        search_user = scholarly.search_author_id(user)
        fullname_affiliation = search_user['name']+', '+search_user['affiliation'].split(",")[-1].strip()
        search_query = scholarly.search_author(fullname_affiliation)
        author = next(search_query)
        data = scholarly.fill(author, sections=[], sortby='year')
        data_all = []
        citations = []
        for pub in data["publications"]:
            gs_view = "https://scholar.google.co.kr/citations?view_op=view_citation&hl=en&citation_for_view="+pub['author_pub_id']
            if pub['num_citations'] > 0:
                gs_link = pub['citedby_url']
            else:
                gs_link = gs_view
            citations.append(pub['num_citations'])
            data_all.append({'title': pub['bib']['title'], 'year': int(pub['bib']['pub_year']), 'citation': pub['num_citations'], 'gs_view': gs_view, 'gs_link': gs_link })
        #data_all.sort(key=lambda x: x.get('year'), reverse=True)
        yearly_publications = yearly_count(data_all)
        yc_citations = {str(key): value for key, value in data['cites_per_year'].items()}
        basic_info = {k: search_user[k] for k in search_user.keys() - {'container_type', 'filled', 'source', 'citedby', 'scholar_id'}}
        # record end time
        time_end = time()
        # calculate the duration
        time_duration = round(time_end - time_start,2)
        info = f'Took {time_duration} seconds'
        db.orcid_googlescholar.find_one_and_update({'user': user},
                               {"$set": {'basic_info': basic_info,'data':data_all, 'total_papers': len(citations), 'total_citations': sum(citations), 'yearly_publications': yearly_publications, 'yc_citations': yc_citations, 'hindex':data['hindex'], 'i10index':data['i10index'], 'gs_id': 'https://scholar.google.co.kr/citations?user='+data['scholar_id'], 'updated': todaydate, 'info':info}},
                               upsert=True)
        data = db.orcid_googlescholar.find_one({'user': user}, {'_id': False})
    return data

def get_orcid_googlescholar(orcid_id, db_request=False):
    # check if data already exist
    data = db.orcid_googlescholar.find_one({'orcid': orcid_id}, {'_id': False})
    if(data and db_request):
        return data
    else:
        today = datetime.today()
        todaydate = today.strftime("%d/%m/%Y %H:%M:%S")
        URL_ORCID = "https://orcid.org/"+str(orcid_id)+"/public-record.json"
        r = requests.get(URL_ORCID, headers=HEADERS)
        orcid_dt = r.json()
        fullname = orcid_dt['displayName']
        search_query = scholarly.search_author(fullname)
        author = next(search_query)
        data = scholarly.fill(author, sections=[], sortby='year')
        data_all = []
        citations = []
        for pub in data["publications"]:
            gs_view = "https://scholar.google.co.kr/citations?view_op=view_citation&hl=en&citation_for_view="+pub['author_pub_id']
            if pub['num_citations'] > 0:
                gs_link = pub['citedby_url']
            else:
                gs_link = gs_view
            citations.append(pub['num_citations'])
            data_all.append({'title': pub['bib']['title'], 'year': int(pub['bib']['pub_year']), 'citation': pub['num_citations'], 'gs_view': gs_view, 'gs_link': gs_link })
        #data_all.sort(key=lambda x: x.get('year'), reverse=True)
        yearly_publications = yearly_count(data_all)
        yc_citations = {str(key): value for key, value in data['cites_per_year'].items()}
        db.orcid_googlescholar.find_one_and_update({'orcid':orcid_id},
                               {"$set": {'data':data_all, 'total_papers': len(citations), 'total_citations': sum(citations), 'yearly_publications': yearly_publications, 'yc_citations': yc_citations, 'hindex':data['hindex'], 'i10index':data['i10index'], 'gs_id': 'https://scholar.google.co.kr/citations?user='+data['scholar_id'], 'updated': todaydate}},
                               upsert=True)
        data = db.orcid_googlescholar.find_one({'orcid': orcid_id}, {'_id': False})
    return data


def get_orcid_crossref(orcid_id, db_request=False):
    # check if data already exist
    data = db.orcid_crossref.find_one({'orcid': orcid_id}, {'_id': False})
    if(data and db_request):
        return data
    else:
        today = datetime.today()
        todaydate = today.strftime("%d/%m/%Y %H:%M:%S")
        headers_config = {'User-Agent': 'Academic Page/0.1.1 (https://github.com/justudin/academic-page; mailto:just.udin@yahoo.com) to retrieve citation counts'}
        URL_ORCID = "https://pub.orcid.org/v3.0/"+str(orcid_id)+"/works"
        r = requests.get(URL_ORCID, headers=HEADERS)
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
                    cross = requests.get(URL_CROSSREF, headers=headers_config)
                    cross_dt = cross.json()
                    citation = cross_dt["message"]["is-referenced-by-count"]
                    citations.append(citation)
                    title = cross_dt["message"]["title"][0]
                    typepaper = cross_dt["message"]["type"]
                    created = cross_dt["message"]["created"]["timestamp"]
                    year = cross_dt["message"]["created"]["date-parts"][0][0]
                    # call cited-by
                    URL_API_CITED_BY = "https://doi.crossref.org/servlet/getForwardLinks?usr={}&pwd={}&doi={}".format(USR_CITED,PWD_CITED,doi)
                    # Generate a cache key based on URL and payload
                    cache_key = hashlib.sha256(json.dumps({'url': URL_API_CITED_BY}).encode('utf-8')).hexdigest()
                    next_day = datetime.now() + timedelta(days=1)
                    # Check if the response is in the cache
                    cached_response = backend.get_response(cache_key)
                    if cached_response is None:
                        # If not cached, make the actual request
                        response = requests.post(URL_API_CITED_BY)
                        # Store the response in the cache manually
                        backend.save_response(response, cache_key, expires=next_day)
                    else:
                        # Use cached response
                        response = cached_response
                    #rq_cited = requests.post(URL_API_CITED_BY, headers=headers_config)
                    my_dict = xmltodict.parse(response.content)
                    yearly_citations_output = get_yearly_citations(my_dict)
                    #print(doi, yearly_citations_output)
                    data_all.append({'title':title, 'doi': doi, 'type':typepaper, 'year':year, 'created':created,'citation':citation, 'yearly_citations': yearly_citations_output})
                data_all.sort(key=lambda x: x.get('year'), reverse=True)
            hIndexScore = hIndex(citations)

            category_publications = categorize_publications(data_all)
            yearly_publications = yearly_count(data_all)
            yc_publications = update_publication_count(data_all)
            yc_citations = citations_yearly_summary(data_all)
            total_citations = sum(yc_citations.values())
            db.orcid_crossref.find_one_and_update({'orcid':orcid_id},
                               {"$set": {'data':data_all, 'total_papers': len(citations), 'total_citations': total_citations, 'category_publications': category_publications, 'yearly_publications': yearly_publications, 'yc_citations':yc_citations, 'yearlycat_publications': yc_publications ,'hindex': hIndexScore, 'updated': todaydate}},
                               upsert=True)
            data = db.orcid_crossref.find_one({'orcid': orcid_id}, {'_id': False})
        return data

def get_orcid_reviews(orcid_id, db_request=True):
    # check if data already exist
    data_mongodb = db.orcid_reviews.find_one({'orcid': orcid_id}, {'_id': False})
    if(data_mongodb and db_request):
        return data_mongodb
    else:
        today = datetime.today()
        todaydate = today.strftime("%d/%m/%Y %H:%M:%S")
        headers_config = {'User-Agent': 'Academic Page/0.1.1 (https://github.com/justudin/academic-page; mailto:just.udin@yahoo.com) to retrieve citation counts'}
        URL_ORCID = "https://orcid.org/"+str(orcid_id)+"/peer-reviews-minimized.json?sortAsc=true"
        r = requests.get(URL_ORCID, headers=HEADERS)
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
            outlet_reviews = defaultdict(lambda: {"issn": "", "reviews": 0})
            for data in data_all:
                outlet_reviews[data["outlet"]]["issn"] = data["issn"]
                outlet_reviews[data["outlet"]]["reviews"] += data["reviews"]
            data_all = [{"outlet": outlet, "issn": info["issn"], "reviews": info["reviews"]} for outlet, info in outlet_reviews.items()]
            data_all.sort(key=lambda x: x.get('reviews'), reverse=True)
            db.orcid_reviews.find_one_and_update({'orcid':orcid_id},
                               {"$set": {'data':data_all, 'total_reviews': total_review, 'total_outlets': len(data_all), 'updated': todaydate}},
                               upsert=True)
            data_mongodb = db.orcid_reviews.find_one({'orcid': orcid_id}, {'_id': False})
        return data_mongodb

def get_reviews(data):
    return data.get('reviews')

@app.errorhandler(404)
def page_not_found(e):
    message = jsonify(error=True, message='The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.')
    return make_response(message, 404)

@app.errorhandler(500)
def internal_server_error(e):
    message = jsonify(error=True, message='Uh Oh. There is something wrong. Please try again later.')
    return make_response(message, 500)

@app.errorhandler(Exception)
def handle_exception(e):
    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return e

    message = jsonify(error=True, message='Uh Oh. There is something wrong. Please try again later.')
    return make_response(message, 500)
    

def deep_get(dictionary, keys, default=None):
    return reduce(lambda d, key: d.get(key, default) if isinstance(d, dict) else default, keys.split("."), dictionary)

def hIndex(citations):
    return sum(x >= i + 1 for i, x in enumerate(sorted(list(citations), reverse=True)))

def get_data_mongodb(data):
    del data['_id']
    data["info"] = "data is not fresh"
    #data['_id'] = str(data['_id'])
    return data

def categorize_publications(publications):
    category_count = {}

    for publication in publications:
        if publication['type'] in category_count:
            category_count[publication['type']] += 1
        else:
            category_count[publication['type']] = 1
    
    return category_count

def yearly_count(publications):
    yearly_publications = {}

    for publication in publications:
        if str(publication['year']) in yearly_publications:
            yearly_publications[str(publication['year'])] += 1
        else:
            yearly_publications[str(publication['year'])] = 1
    
    return yearly_publications

def update_publication_count(publications):
    publications_count = {}
    for publication in publications:
        # Ensure the year key exists
        if publication['year'] not in publications_count:
            publications_count[str(publication['year'])] = {}
        
        # Ensure the category key exists
        if publication['type'] not in publications_count[str(publication['year'])]:
            publications_count[str(publication['year'])][publication['type']] = 0

        # Increment the count for the given category in the specified year
        publications_count[str(publication['year'])][publication['type']] += 1

    return publications_count

def citations_yearly_summary(publications):
    citations_yearly_count = {}
    for publication in publications:
        yearly_citations = publication.get('yearly_citations', {})
        if isinstance(yearly_citations, dict):
            for year, count in yearly_citations.items():
                if year in citations_yearly_count:
                    citations_yearly_count[str(year)] += count
                else:
                    citations_yearly_count[str(year)] = count
    return citations_yearly_count

# Function to get dictionary values using keys with a specific suffix
def get_values_with_suffix(data, suffix='_cite'):
    #return {"cited": v for k, v in d.items() if k.endswith(suffix)}
    def extract_values(d):
            return {"cited": v for k, v in d.items() if k.endswith(suffix)}
        
    if isinstance(data, dict):
        return extract_values(data)
    elif isinstance(data, list):
        return [extract_values(d) for d in data if isinstance(d, dict)]
    else:
        raise TypeError("Input must be a dictionary or a list of dictionaries")

def get_yearly_citations(my_dict):
    yearly_citations = {}
    checkKey = safe_get_try_except(my_dict['crossref_result']['query_result']['body'], 'forward_link')
    if checkKey is not None:
        forward_link = my_dict['crossref_result']['query_result']['body']['forward_link']
        if isinstance(forward_link, dict):
            values_with_suffix = get_values_with_suffix(forward_link)
            year = values_with_suffix['cited']['year']
            if year in yearly_citations:
                yearly_citations[year] += 1
            else:
                yearly_citations[year] = 1
        elif isinstance(forward_link, list):
            for x in list(forward_link):
                values_with_suffix = get_values_with_suffix(x)
                year = values_with_suffix['cited']['year']
                if year in yearly_citations:
                    yearly_citations[year] += 1
                else:
                    yearly_citations[year] = 1
            
        return yearly_citations
    else:
        pass

def safe_get_try_except(d, key, default=None):
    try:
        return d[key]
    except TypeError:
        return default
    except KeyError:
        return default