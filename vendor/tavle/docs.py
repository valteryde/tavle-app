
from flask import Blueprint
from werkzeug.routing import Rule, Map
from api import BoardsResource, BoardResource, BoardTokenResource, StrokesResource, StrokeResource, ImagesResource, ImageResource

docs_bp = Blueprint('docs_bp', __name__)


def extract_route_details(route_string):
    # 1. Create a Map to provide the converter registry
    m = Map()
    rule = Rule(route_string)
    
    # 2. Bind the rule to the map. 
    # This populates rule._trace and rule._converters
    rule.bind(m)

    details = []
    
    # 3. Iterate through _trace to find dynamic segments
    # _trace is a list of (is_dynamic, value)
    for is_dynamic, value in rule._trace:
        if is_dynamic:
            # 'value' is the name of the variable (e.g., 'user_id')
            # Look up the converter object created during binding
            converter = rule._converters[value]
            
            details.append({
                "variable": value,
                "converter_type": type(converter).__name__.replace('Converter', '').lower(),
                # regex is useful if you want to validate the docs
                "regex": converter.regex 
            })
            
    return details



def retrieve_endpoint_docs(resource, endpoint):
    """
    Retrieve documentation for a given resource.
    
    
     {
        'method': 'GET',
        'path': '/api/boards',
        'description': 'List all boards',
        'parameters': [],
        'response': {
            'boards': '[array of board objects]',
            'count': 'number'
        }
    },

    """

    parameters = extract_route_details(resource.url)
    method = getattr(resource, endpoint.lower())

    parser = getattr(resource(), 'parser', None)

    desc = getattr(method, '__doc__', None)
    if desc:
        desc = desc.strip()

    return {
        'method': endpoint.upper(),
        'path': resource.url,
        
        # Get the docstring of the method if available
        'description': desc,
        
        # Automatically extract parameters from the URL
        'parameters': [
            {
                'name': part["variable"],
                'type': part["converter_type"],
                'required': True,
                'in': 'path',
                'description': f'{part["variable"]} parameter from URL'
            }
            for part in parameters
        ] + [
            # Additional parameters can be added here if needed
            {'name': arg.name,
             'type': getattr(arg.type, "__name__", str(arg.type)), 
             'in': 'body',
             'required': arg.required,
             'description': getattr(arg, 'help', None) or f'Body parameter: {arg.name}'
            }
            for arg in parser.args
        ],

        # Returns 
        "response": getattr(method, 'response',  "")
    }


@docs_bp.route('/api/docs', methods=['GET'])
def get():
    """Return auto-generated API documentation based on registered resources."""
    docs = {
        'title': 'Whiteboard API',
        'version': '1.0',
        'base_url': '/api',
        'authentication': {
            'type': 'Bearer Token',
            'header': 'Authorization: Bearer <admin_token>',
            'description': 'All endpoints require admin API token authentication'
        },
        'endpoints': []
    }
    
    
    resources = [BoardsResource, BoardResource, BoardTokenResource, StrokesResource, StrokeResource]

    resource_docs = []

    for resource in resources:    
        resource_docs.append({
            'resource': resource.__name__.replace('Resource', ''),
            'description': getattr(resource, 'desc', ''),
            'endpoints': [
                # {
                #     'method': 'GET',
                #     'path': '/api/boards',
                #     'description': 'List all boards',
                #     'parameters': [],
                #     'response': {
                #         'boards': '[array of board objects]',
                #         'count': 'number'
                #     }
                # },
                retrieve_endpoint_docs(resource, endpoint)
                for endpoint in resource.__dict__.get('methods', [])
            ]
        })
        
    docs['resources'] = resource_docs
    
    return docs, 200
