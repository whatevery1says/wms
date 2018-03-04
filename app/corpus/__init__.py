import os, tabulator, itertools, requests, json, re, zipfile, shutil
# from datetime import datetime
from jsonschema import validate, FormatChecker
# from tabulator import Stream
# import pandas as pd
# from tableschema_pandas import Storage
from flask import Blueprint, render_template, request, url_for, current_app, send_file
from werkzeug.utils import secure_filename

import pymongo
from pymongo import MongoClient

# Set up the MongoDB client, configure the databases, and assign variables to the "collections" 
client = MongoClient('mongodb://localhost:27017')
db = client.we1s
corpus_db = db.Corpus

corpus = Blueprint('corpus', __name__, template_folder='corpus')

from app.corpus.helpers import methods as methods

#----------------------------------------------------------------------------#
# Constants.
#----------------------------------------------------------------------------#

ALLOWED_EXTENSIONS = ['xlsx']

#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#

@corpus.route('/')
def index():
	"""Corpus index page."""
	scripts = ['js/corpus/corpus.js']
	return render_template('corpus/index.html', scripts=scripts)


@corpus.route('/create', methods=['GET', 'POST'])
def create():
	"""Create manifest page."""
	scripts = ['js/parsley.min.js', 'js/corpus/corpus.js']
	breadcrumbs = [{'link': '/corpus', 'label': 'Corpus'}, {'link': '/corpus/create', 'label': 'Create Collection'}]
	return render_template('corpus/create.html', scripts=scripts, breadcrumbs=breadcrumbs)


@corpus.route('/create-manifest', methods=['GET', 'POST'])
def create_manifest():
	""" Ajax route for creating manifests."""
	errors = []
	data = request.json
	data['namespace'] = 'we1sv1.1'
	# Set id and path by branch
	if data['nodetype'] == 'collection':
		data['path'] = ',Corpus,'
	elif data['nodetype'] in ['RawData', 'ProcessedData', 'Metadata', 'Outputs', 'Results']:
		data['_id'] = data['nodetype']
	else:
		pass
	if not data['path'].startswith(',Corpus,'):
		data['path'] = ',Corpus,' + data['path']
	if not data['path'].endswith(','):
		data['path'] += ','
	# Remove empty values
	manifest = {}
	for key, value in data.items():
		if value != '':
			manifest[key] = value
	# Handle dates
	if 'date' in manifest.keys():
		dates = manifest['date'].splitlines()
		dates = [x.strip() for x in dates]
		new_dates, error_list = methods.check_date_format(dates)
		errors = errors + error_list
		manifest['date'] = dates
	# Handle other textarea strings
	list_props = ['publications', 'collectors', 'queryterms', 'processes', 'notes']
	for item in list_props:
		if item in manifest:
			ls = manifest[item].splitlines()
			manifest[item] = [x.strip() for x in ls]
	nodetype = manifest.pop('nodetype', None)
	# Validate the resulting manifest
	if methods.validate_manifest(manifest, nodetype) == True:
		database_errors = methods.create_record(manifest)
		errors = errors + database_errors
	else:
		msg = '''A valid manifest could not be created with the 
		data supplied. Please check your entries against the 
		<a href="/schema" target="_blank">manifest schema</a>.''' 
		errors.append(msg)

	manifest = json.dumps(manifest, indent=2, sort_keys=False)
	if len(errors) > 0:
		error_str = '<ul>'
		for item in errors:
			error_str += '<li>' + item + '</li>'
		error_str += '</ul>'
	else:
		error_str = ''
	response = {'manifest': manifest, 'errors': error_str}
	return json.dumps(response)


@corpus.route('/display/<_id>')
def display(_id):
	""" Page for displaying Corpus manifests."""
	scripts = ['js/parsley.min.js', 'js/corpus/corpus.js']
	breadcrumbs = [{'link': '/corpus', 'label': 'Corpus'}, {'link': '/corpus/display', 'label': 'Display Collection'}]
	errors = []
	manifest = {}
	try:
		result = corpus_db.find_one({'_id': _id})
		assert result != None
		for key, value in result.items():
			if isinstance(value, list):
				manifest[key] = '\n'.join(value)
			else:
				manifest[key] = value
		# Get a nodetype to determine which form to display
		if manifest['path'] == ',Corpus,':
			nodetype = 'collection'
		elif manifest['_id'] in ['RawData', 'ProcessedData', 'Metadata', 'Outputs', 'Results']:
			nodetype = manifest['_id'].lower()
		else:
			nodetype = 'branch'
	except:
		errors.append('Unknown Error: The manifest does not exist or could not be loaded.')
	return render_template('corpus/display.html', scripts=scripts,
		breadcrumbs=breadcrumbs, manifest=manifest, errors=errors,
		nodetype=nodetype)


@corpus.route('/update-manifest', methods=['GET', 'POST'])
def update_manifest():
	""" Ajax route for updating manifests."""
	errors = []
	data = request.json
	print(data)
	data['namespace'] = 'we1sv1.1'
	# Set id and path by branch
	if data['path'] == ',Corpus,':
		data['nodetype'] = 'collection'
	elif data['_id'] in ['RawData', 'ProcessedData', 'Metadata', 'Outputs', 'Results']:
		data['nodetype'] = data['_id']
	else:
		data['nodetype'] = 'branch'
	if not data['path'].startswith(',Corpus,'):
		data['path'] = ',Corpus,' + data['path']
	if not data['path'].endswith(','):
		data['path'] += ','
	# Remove empty values
	manifest = {}
	for key, value in data.items():
		if value != '':
			manifest[key] = value
	# Handle dates
	if 'date' in manifest.keys():
		dates = manifest['date'].splitlines()
		dates = [x.strip() for x in dates]
		new_dates, error_list = methods.check_date_format(dates)
		errors = errors + error_list
		manifest['date'] = dates
	# Handle other textarea strings
	list_props = ['publications', 'collectors', 'queryterms', 'processes', 'notes']
	for item in list_props:
		if item in manifest:
			ls = manifest[item].splitlines()
			manifest[item] = [x.strip() for x in ls]
	nodetype = manifest.pop('nodetype', None)
	# Validate the resulting manifest
	if methods.validate_manifest(manifest, nodetype) == True:
		database_errors = methods.update_record(manifest)
		errors = errors + database_errors
	else:
		msg = '''A valid manifest could not be created with the 
		data supplied. Please check your entries against the 
		<a href="/schema" target="_blank">manifest schema</a>.''' 
		errors.append(msg)

	manifest = json.dumps(manifest, indent=2, sort_keys=False)
	if len(errors) > 0:
		error_str = '<ul>'
		for item in errors:
			error_str += '<li>' + item + '</li>'
		error_str += '</ul>'
	else:
		error_str = ''
	response = {'manifest': manifest, 'errors': error_str}
	return json.dumps(response)


@corpus.route('/send-export', methods=['GET', 'POST'])
def send_export():
	""" Ajax route to process user export options and write 
	the export files to the temp folder.
	"""
	data = request.json
	# The user only wants to print the manifest
	if data['exportoptions'] == ['manifestonly']:
		query = {'_id': data['_id'], 'path': data['path']}
		try:
			result = corpus_db.find_one(query)
			assert result != None
			manifest = {}
			for key, value in result.items():
				if value != '' and value != []:
					manifest[key] = value
			manifest = json.dumps(manifest, indent=2, sort_keys=False)
			filename = data['_id'] + '.json'
			doc = filename
			methods.make_dir('app/temp')
			filepath = os.path.join('app/temp', filename)
			with open(filepath, 'w') as f:
				f.write(manifest)
		except:
			print('Could not find the manifest in the database.')
	# The user wants a zip of multiple data documents
	else:
		# Get the exportoptions with the correct case
		make_dir('app/temp/Corpus')
		id = data['_id']
		path = data['path']
		# Ensures that there is a Corpus and collection folder with a collection manifest
		methods.make_dir('app/temp/Corpus')
		if path == ',Corpus,':
			collection = id
		else:
			collection = path.split(',')[2]
		methods.make_dir('app/temp/Corpus/' + collection)
		result = corpus_db.find_one({'path': path, '_id': collection})
		assert result != None
		manifest = {}
		for key, value in result.items():
			if value != '' and value != []:
				manifest[key] = value
		manifest = json.dumps(manifest, indent=2, sort_keys=False)
		filename = id + '.json'
		filepath = os.path.join('app/temp/Corpus', filename)
		with open(filepath, 'w') as f:
			f.write(manifest)
		exportoptions = []
		exportopts = [x.replace('export', '') for x in data['exportoptions']]
		exclude = []
		options = ['Corpus', 'RawData', 'ProcessedData', 'Metadata', 'Outputs', 'Results']
		if not path.startswith(',Corpus,'):
			path = ',Corpus,' + path
		for option in options:
			if option.lower() in exportopts:
				exportoptions.append(option)
			else:
				exclude.append(',Corpus,' + ',' + id + ',' + option + ',.*')
		# We have a path and a list of paths to exclude
		excluded = '|'.join(exclude)
		excluded = re.compile(excluded)
		regex_path = re.compile(path + id + ',.*')
		result = corpus_db.find(
			{'path': {
				'$regex': regex_path,
				'$not': excluded
			}}
		)
		for item in list(result):
			# Handle schema node manifests
			path = item['path'].replace(',', '/')
			if item['_id'] in exportoptions:
				folder_path = os.path.join(path, item['_id'])
				methods.make_dir('app/temp' + folder_path)
				folder = 'app/temp' + path
				doc = item['_id'] + '.json'
			# Handle data and branches
			else:
				# If the document has content, just give it a filename
				try:
					assert item['content']
					doc = item['_id'] + '.json'
					folder = 'app/temp' + path
					methods.make_dir(folder)
				# Otherwise, use it to create a folder with a manifest file
				except:
					path = os.path.join(path, item['_id'])
					folder = 'app/temp' + path
					methods.make_dir(folder)
					doc = item['_id'] + '.json'
			filepath = os.path.join(folder, doc)
			output = json.dumps(item, indent=2, sort_keys=False)
			with open(filepath, 'w') as f:
				f.write(output)
		# Zip up the file structure
		try:
			source_dir = 'app/temp/Corpus'
			doc = 'Corpus.zip'
			methods.zipfolder(source_dir, source_dir)
		except:
			print('Could not make zip archive.')
	return json.dumps({'filename': doc})


@corpus.route('/download-export/<filename>', methods=['GET', 'POST'])
def download_export(filename):
	""" Ajax route to trigger download and empty the temp folder."""
	from flask import make_response
	filepath = os.path.join('app/temp', filename)
	# Can't get Firefox to save the file extension by any means
	with open(filepath, 'rb') as f:
		response = make_response(f.read())
	os.remove(filepath)
	response.headers['Content-Type'] = 'application/octet-stream'
	response.headers["Content-Disposition"] = "attachment; filename={}".format(filename)
	# As a precaution, empty the temp folder
	shutil.rmtree('app/temp')
	methods.make_dir('app/temp')
	return response


@corpus.route('/search', methods=['GET', 'POST'])
def search():
	""" Page for searching Corpus manifests."""
	scripts = ['js/parsley.min.js', 'js/jquery.twbsPagination.min.js', 'js/corpus/corpus.js']
	breadcrumbs = [{'link': '/corpus', 'label': 'Corpus'}, {'link': '/corpus/search', 'label': 'Search Collections'}]
	if request.method == 'GET':
		return render_template('corpus/search.html', scripts=scripts, breadcrumbs=breadcrumbs)
	if request.method == 'POST':
		result, num_pages, errors = methods.search_collections(request.json)
		if result == []:
			errors.append('No records were found matching your search criteria.')
		return json.dumps({'response': result, 'num_pages': num_pages, 'errors': errors})


@corpus.route('/export-search', methods=['GET', 'POST'])
def export_search():
	""" Ajax route for exporting search results."""
	if request.method == 'POST':
		result, num_pages, errors = methods.search_collections(request.json)
		if len(result) == 0:
			errors.append('No records were found matching your search criteria.')
		# Need to write the results to temp folder
		for item in result:
			filename = item['_id'] + '.json'
			filepath = os.path.join('app/temp', filename)
			with open(filepath, 'w') as f:
				f.write(json.dumps(item, indent=2, sort_keys=False))
		# Need to zip up multiple files
		if len(result) > 1:
			filename = 'search_results.zip'
			methods.zipfolder('app/temp', 'search_results')
		return json.dumps({'filename': filename, 'errors': errors})


@corpus.route('/delete-manifest', methods=['GET', 'POST'])
def delete_manifest():
	""" Ajax route for deleting manifests."""
	errors = []
	msg = methods.delete_collection(request.json['id'])
	if msg  != 'success':
		errors.append(msg)
	return json.dumps({'errors': errors})


@corpus.route('/import', methods=['GET', 'POST'])
def import_data():
	""" Page for importing manifests."""
	scripts = [
	'js/corpus/dropzone.js',
	'js/parsley.min.js', 
	'js/corpus/corpus.js',
	'js/corpus/upload.js'
	]
	breadcrumbs = [{'link': '/corpus', 'label': 'Corpus'}, {'link': '/corpus/import', 'label': 'Import Collection Data'}]
	return render_template('corpus/import.html', scripts=scripts, breadcrumbs=breadcrumbs)


@corpus.route('/remove-file', methods=['GET', 'POST'])
def remove_file():
	"""Ajax route triggered when a file is deleted from the file
	uploads table. This function ensures that it is removed from
	both the database and the uploads folder.
	"""
	if request.method == 'POST':
		# Delete the record (if it exists) from the database
		collection = request.json['collection']
		if collection.startswith(',Corpus,'):
			collection = collection.replace(',Corpus,', '')
		path = ',Corpus,' + collection + ',' + request.json['category'] + ','
		if request.json['branch'] != '':
			path = path + request.json['branch'] + ','
		filename = request.json['filename'] 
		_id = filename.strip('.json')
		corpus_db.delete_one({'path': path, '_id': _id})
		# Now delete the file (if it exists) in the uploads folder
		mydir = os.path.join('app', current_app.config['UPLOAD_FOLDER'])
		myfile = os.path.join(mydir, filename)
		# The removal should only fail if there is no DB entry or file to remove.
		# So no need to handle errors.
		return json.dumps({'response': 'success'})


@corpus.route('/save-upload', methods=['GET', 'POST'])
def save_upload():
	""" Ajax route to create a manifest for each uploaded file  
	and insert it in the database.
	"""
	if request.method == 'POST':
		errors = []
		# Handle the form data
		exclude = ['branch', 'category', 'collection']
		node_metadata = {}
		for key, value in request.json.items():
			if key not in exclude and value != '' and value != []:
				node_metadata[key] = value
		# Set the _id and path
		if request.json['collection'].startswith(',Corpus,'):
			collection = request.json['collection']
		else:
			collection = ',Corpus,' + request.json['collection']
		# Make sure the collection exists in the database
		try:
			result = list(corpus_db.find({'path': ',Corpus,', '_id': request.json['collection']}))
			assert result != []
			# Set the _id and path for the new manifest
			node_metadata = {}
			if request.json['branch'] != '':
				node_metadata['_id'] = request.json['branch']
				node_metadata['path'] = collection + request.json['category'] + ','
			else:
				node_metadata['_id'] = request.json['category']
				node_metadata['path'] = collection + ','
			mydir = os.path.join('app', current_app.config['UPLOAD_FOLDER'])
			# Make sure files exist in the uploads folder
			if len(os.listdir(mydir)) > 0:
				# If the category or branch node does not exist, create it
				if len(list(corpus_db.find({'_id': node_metadata['_id'], 'path': node_metadata['path']}))) == 0:
					print('Node does not exist. Creating one.')					
					corpus_db.insert_one(node_metadata)
				# Now start creating a data manifest for each file and inserting it
				for filename in os.listdir(mydir):
					filepath = os.path.join(mydir, filename)
					path = node_metadata['path'] + node_metadata['_id'] + ','
					manifest = {'_id': filename.strip('.json'), 'namespace': 'we1sv1.1', 'path': path}
					try:
						with open(filepath, 'rb') as f:
							doc = json.loads(f.read())
							for key, value in doc.items():
								if key not in ['_id', 'namespace', 'path']:
									manifest[key] = value
					except:
						errors.append('<p>The file <code>' + filename + '</code> could not be loaded or it did not have a <code>content</code> property.')
					schema_file = 'https://raw.githubusercontent.com/whatevery1says/manifest/master/schema/Corpus/Data.json'
					schema = json.loads(requests.get(schema_file).text)
					try:
						methods.validate(manifest, schema, format_checker=FormatChecker())
						result = methods.create_record(manifest)
						errors = errors + result
					except:
						print('Could not validate manifest for ' + filename)
						errors.append('<p>A valid manifest could not be created from the file <code>' + filename + '</code> or the manifest could not be added to the database due to an unknown error.')
				# We're done. Empty the uploads folder.
				mydir = os.path.join('app', current_app.config['UPLOAD_FOLDER'])
				list(map(os.unlink, (os.path.join(mydir,f) for f in os.listdir(mydir))))
			else:
				print('There were no files in the uploads directory.')
		except:
			errors.append('<p>The specified collection does not exist in the database. Check your entry or <a href="/corpus/create">Create a Collection</a> before importing data.</p>')
		if errors == []:			
			response = {'response': '<p>Manifests created successfully.</p>'}
		else:
			response = {'errors': errors}
		return json.dumps(response)


@corpus.route('/upload', methods=['GET', 'POST'])
def upload():
	"""Ajax route saves each file uploaded by the import function
	to the uploads folder.
	"""
	if request.method == 'POST':
		errors = []
		for file in request.files.getlist('file'):
			# Accept only json files for now...
			if file.filename.endswith('.json'):
				try:
					filename = secure_filename(file.filename)
					file_to_save = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
					file_to_save = os.path.join('app', file_to_save)
					file.save(file_to_save)
				except:
					errors.append('<p>Unknown Error: Could not save the file <code>' + filename + '</code>.</p>')
			else:
				errors.append('<p>The file <code>' + file.filename + '</code> has an invalid file type.</p>')					
		if errors == []:			
			response = {'response': 'file(s) saved successfully'}
		else:
			response = {'errors': errors}
		return json.dumps(response)					


@corpus.route('/clear')
def clear():
	""" Going to this page will quickly empty the datbase.
	Disable this for production.
	"""
	corpus_db.delete_many({})


@corpus.route('/search2', methods=['GET', 'POST'])
def search2():
	""" Page for searching Corpus manifests."""
	scripts = ['js/query-builder.standalone.js', 'js/moment.min.js', 'js/jquery.twbsPagination.min.js', 'js/corpus/corpus.js', 'js/corpus/search.js']
	styles = ['css/query-builder.default.css']	
	breadcrumbs = [{'link': '/corpus', 'label': 'Corpus'}, {'link': '/corpus/search', 'label': 'Search Collections'}]
	if request.method == 'GET':
		return render_template('corpus/search2.html', scripts=scripts, styles=styles, breadcrumbs=breadcrumbs)
	if request.method == 'POST':
		query = request.json['query']
		query = {}
		page = request.json['page']
		limit = request.json['limit']
		show_properties = request.json['show_properties']
		paginated = True
		# result = list(corpus_db.find(
		# 	query)
		# 	#projection=show_properties)
		# )
		# num_pages = 1
		# errors = []
		# print(result)
		result, num_pages, errors = methods.search_corpus(query, limit, paginated, page, show_properties)
		print(result)
		if result == []:
			errors.append('No records were found matching your search criteria.')
		return json.dumps({'response': result, 'num_pages': num_pages, 'errors': errors})

