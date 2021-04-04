import pyodbc
from enum import Enum
from abc import ABC
import csv
import pytbls.exceptions
from pytbls.sql import SQLBuilder 
from tabulate import tabulate 

class TableDefinition(object):

	def __init__(self, definition, tablename, schema, *args, create_col_defs=True):
		self._columns = {}
		self._name = tablename
		self._schema = schema
		# Initialize Column def objects if not provided 
		if create_col_defs:
			for col_def in definition:
				try:
					self._columns[col_def['name']] = ColumnDefinition(col_def)
				except KeyError:
					raise ValueError('Name is a required attribute for Column')
		else:
			self.columns = definition

		# Set primary key
		pks = [col for col in self.columns if col.is_pk]
		self._primary_key = pks

		# Set identity column 
		id_col = [col for col in self.columns if col.is_identity]
		if id_col:
			if len(primary_key_col) > 1:
				raise pytbls.exceptions.IllegalTableDefinitionError('Table cannot have more than 1 identity column')
			self._identity = id_col
		else:
			self._identity = None


	@property
	def schema(self):
		return self._schema
	
	@property
	def identity(self):
		return self._identity

	@property
	def composite_key(self):
		return len(self.primary_key) > 1
	
	

	@property
	def name(self):
		return self._name
	

	@property
	def primary_key(self):
		return self._primary_key

	@property
	def column_names(self):
		"""Returns a list of all column names"""
		return [col.name for col in self.columns]

	@property
	def pk_column_names(self):
		return [col.name for col in self.primary_key]
	

	@property
	def required_columns(self):
		"""Returns a list of non-nullable column objects"""
		return [col for col in self.columns if not col.is_nullable]

	@property
	def required_column_names(self):
		"""Returns a list of non-nullable column names"""
		return [col.name for col in self.columns if not col.is_nullable]

	@property
	def columns(self):
		return [col for name, col in self._columns.items()]

	def __iter__(self):
		return iter(self.columns)
	

class MappyTable(TableDefinition):

	def __init__(self, driver, tabledef, tablename, *args):
		super().__init__(tabledef, tablename, *args, create_col_defs=True)
		self.__driver = driver


	def get_import_csv(self, dest, required_only=True, include_index=False, *args):

		if not required_only:
			if len(args) > 0:
				raise ValueError("Cannot specify additional columns if required_only is False")
			headers = self.column_names
		else:
			headers = self.required_column_names
			if args:
				headers.append(args)

		if not include_index:
			headers.remove(self.primary_key.name)

		write_csv(dest, headers, None)

	def update(self, update_dict, pk=None):
		
		composite_key = type(pk) == list 
		update_cols, pks = self.__validate_update_by_pk(update_dict)
		sql_update = SQLBuilder.update(self.name, update_cols, pks)
		self.__driver.write(sql_update, *update_dict.values())


	def __validate_update_by_pk(self, data_dict):
		"""Checks that each PK col is present in the update_dict"""

		pk_cols = []
		for pk_col in self.pk_column_names:
			if pk_col not in data_dict.keys():
				raise pytbls.exceptions.DataValidationError("Primary key '{}' is required for update".format(pk_col))
			pk_cols.append(pk_col)

		update_cols = []
		for key, val in data_dict.items():
			if key not in self.column_names:
				raise pytbls.exceptions.DataValidationError("Attribute '{}' doesn't exist on {} and cannot be updated".format(self.name, key))
			
			if key not in self.pk_column_names:
				update_cols.append(key)

		if len(update_cols) > 0:
			return (pk_cols, update_cols)

		raise pytbls.exceptions.DataValidationError("No columns specified in the update dictionary")

	def add(self, data_dict, commit=True, **data):
		data_dict.update(data)
		insertable = self.__validate_insert(data_dict)
		sql_insert = SQLBuilder.insert(self.name, insertable.keys())
		row_id = self.__driver.write(sql_insert, *insertable.values())

		if self.identity:
			insertable[self.primary_key.name] = row_id

		return insertable

	def __validate_insert(self, data_dict, exact_match=False):
		"""Checks that all columns required for insert are present.
		   and returns a dict of insertable data (removes extra columns)
		"""

		for column in self.required_columns:
			if column.name not in data_dict.keys():
				if not column.is_identity and not column.default_value:
					raise pytbls.exceptions.DataValidationError("Attribute '{}' is required and is None".format(column.name))

		# Parse out columns that can be inserted 
		if not exact_match:
			insertable = {}
			for col, val in data_dict.items():
				if col in self.column_names: 
					insertable[col] = val
			return insertable

		return data_dict


	# Old function def that relied on MappyRow
	# def add(self, data_dict, commit=True, **data):
	# 	data_dict.update(data)
	# 	row = MappyRow(self, data_dict)
	# 	row_id = self.__driver.write(row.sql_insert, row.values)
	# 	row.set_pk(row_id)
	# 	return row

	def test_data(self, data_dict, **data):
		pass


	def add_all(self, data_list, chunksize=None):
		pass

	def print_info(self):
		data = [col.definition for col in self.columns]
		headers = list(data[0].keys())
		data = [col.values() for col in data]
		print(tabulate(data, headers=headers))
	

class ColumnDefinition(object):

	def __init__(self, definition, **kwargs):
		definition.update(kwargs)
		self._definition = definition
		if type(definition) is dict or kwargs:
			try:
				self._name = definition.get('name') or kwargs.get('name')
				self._max_length = definition.get('max_length') or kwargs.get('max_length')
				self._scale = definition.get('scale') or kwargs.get('scale')
				self._is_nullable = definition.get('is_nullable') or kwargs.get('is_nullable')
				self._data_type = definition.get('type') or kwargs.get('type')
				self._column_id = definition.get('column_id') or kwargs.get('column_id')
				self._is_pk = definition.get('is_primary_key')
				self._is_identity = definition.get('is_identity')
				self._default_value = definition.get('default_value')
			except KeyError as e:
				raise ValueError('Required column attribute not set: {}'.format(e.args[0]))
		else:
			raise ValueError('Column attributes not provided to Column Definition object')

	@property
	def is_identity(self):
		return self._is_identity

	@property
	def default_value(self):
		return self._default_value
	
	

	@property
	def definition(self):
		return self._definition
	

	@property
	def is_pk(self):
		return self._is_pk
	

	@property
	def name(self):
		return self._name

	@property
	def max_length(self):
		return self._max_length

	@property
	def scale(self):
		return self._scale

	@property
	def is_nullable(self):
		return self._is_nullable

	@property
	def required(self):
		return self.is_nullable
	

	@property
	def data_type(self):
		return self._data_type

	@property
	def column_id(self):
		return self._column_id
	
	def __str__(self):
		return self.name

	def __repr__(self):
		return 'Column(name: {})'.format(self.name)

	def __eq__(self, other):
		if isinstance(other, ColumnDefinition):
			return other.name == self.name
		return False

	def __hash__(self):
		return hash(self.name)
	
	
class MappyRow(object):
	def __init__(self, tabledef, data_row, **data):
		self._tabledef = tabledef
		data_row.update(data)
		self._data_row = data_row
		self.__validate()

	def set_pk(self, value):
		pk = self.tabledef.primary_key
		if pk in self.data_row or self.data_row.get(pk) is not None:
			raise DataValidationError('Primary key has already been set for this row')
		self.__update(pk, value)

	def __update(self, key, value):
		if key in self.tabledef.columns:
			self.data_row[key.name] = value
		else:
			raise pytbls.exceptions.DataValidationError("Attribute '{}' does not exist on table {}".format(key, self.tabledef.name))

	@property
	def unmatched_data(self):
		return {k:v for k, v in self.data_row.items() if k not in self.tabledef.column_names}
	
	@property
	def values(self):
		matched_values = [v for k, v in self.data_row.items() if k in self.tabledef.column_names]
		return matched_values

	@property
	def column_names(self):
		return [k for k, v in self.data_row.items() if k in self.tabledef.column_names]
	

	@property
	def tabledef(self):
		return self._tabledef

	@property
	def data_row(self):
		return self._data_row

	@property
	def sql_insert(self):
		num_values = len(self.column_names)
		sql = 'INSERT INTO {} ('.format(self.tabledef.name)
		sql += ('{}, ' * (num_values - 1) + '{})\n').format(*self.column_names)
		sql += 'VALUES ('
		sql += ('?, ' * (num_values - 1) + '?)')
		return sql

	def __validate(self):
		pk_name = self.tabledef.primary_key.name
		for column in self.tabledef.required_columns:
			if column.name not in self.data_row and column.name != pk_name:
				raise pytbls.exceptions.DataValidationError("Attribute '{}' is required and is None".format(column.name))

	def __getitem__(self, key):
		return self.data_row[key]

	def __setitem(self, key, value):
		self.__update(key, value)


	def __repr__(self):
		"""Returns repr for dictionary of all data
		   Change to only print staged data 
		"""
		return self.data_row.__repr__()

	
	


def write_csv(filename, headers, data):
	with open(filename, 'w', newline='') as csvfile:
		writer = csv.DictWriter(csvfile, fieldnames=headers)
		writer.writeheader()
		if data:
			for row in data:
				writer.writerow(row)

def read_csv(filename, read_empty_as_none=True, strip=True):
	data = []
	with open(filename) as f:
		data_reader = csv.DictReader(f)
		for row in data_reader:
			if read_empty_as_none:
				row = {k: read_blank_as if v == '' else v for k, v in row.items()}
			data.append(dict(row))

	return data


def print_dict_as_table(d, PADDING=2, FORMAT_CHAR='-'):
	headers = d.keys()
	data = d.values()
	print_as_table(table_headers=headers, data=data)

def print_as_table(table_headers=[], data=[], PADDING=2, FORMAT_CHAR='-'):
	column_lens = __get_max_col_widths(table_headers, data)
	TABLE_LEN = (sum((column_lens[header] + PADDING + 1) 
				for header in table_headers))

	row_format = "|{:^{width}}"
	# print line
	print(FORMAT_CHAR * (TABLE_LEN + 1))

	# Print column headers
	for header in table_headers:
		width = column_lens[header] + PADDING
		print(row_format.format(header, width=width), end='')
	print('|')
	print(FORMAT_CHAR * (TABLE_LEN + 1))

	# Print data
	for row in data:
		for tup, column_len in zip(row.values(), column_lens.values()):	
			width = column_len + PADDING
			print(row_format.format(tup, width=width), end='')
		print("|")
	
def __get_max_col_widths(table_headers, data):
	column_lens = {}
	for header in table_headers:
		max_data_len = max([len(str(item[header])) for item in data])
		column_lens[header] = max(max_data_len, len(header))

	for k, v in column_lens.items():
		print(k, v)

	return column_lens

