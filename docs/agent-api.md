# The agent API

`buildzr serve` does more than show the diagrams. For every [site](cli.md) it also answers questions about the architecture as JSON, so a program, an AI assistant or a person with `curl` can ask "what talks to the database?" without opening the viewer and without knowing anything about the Python code that produced the model.

The API is **read-only**. It only answers `GET` (and `HEAD`). It lives next to the viewer, at `api/v1/` below the site's address:

```text
$ buildzr build -w examples/buildzr_models_example.py
/home/you/buildzr/examples/buildzr_models_example.py: 13 elements, 6 relationships, 1 views, 5 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built .buildzr/site (13 elements, 6 relationships, 1 view; modelHash sha256:ea077dc27381…)

$ buildzr serve
Serving /home/you/buildzr/.buildzr/site at http://127.0.0.1:8000/ (Ctrl+C to stop)
Agent API at http://127.0.0.1:8000/api/v1/ (read only)
```

Then ask with any HTTP client, for example `curl -s http://127.0.0.1:8000/api/v1/`. You will get the orientation document shown below.

The examples below were produced by running these calls against the site built from `examples/buildzr_models_example.py`. They show the default output of `buildzr serve`, without `--public-url`.

## Words used here

| Word | Meaning |
|---|---|
| **element** | A person, a software system, a container (an application or data store inside a system) or a component (a part inside a container). |
| **id** | The element's path of lower-case names, joined by `/`: `e-commerce-system/web-app` is the Web App inside the E-Commerce System. Two siblings with the same name get `-2`, `-3`. Ids are given in query parameters: `?id=e-commerce-system/web-app`. |
| **relationship** | An explicit "A uses B" statement written in the model, with a description and sometimes a technology. Its id is `<source id>-><destination id>`, plus `:<description>` when two relationships connect the same pair. |
| **rollup** | An arrow between two big boxes stands for every relationship between what is inside them. This API follows the same rule as the viewer: a relationship of a descendant counts for its ancestors. |
| **view** | A diagram the authors chose to draw (for example a system context view), as opposed to the free browsing the viewer offers. |
| **modelHash** | A fingerprint of the model. The same model always has the same hash, and every answer carries it. |

## The orientation document

`GET api/v1/` tells a reader what the model is, how big it is and how to ask. Start here.

```http
GET /api/v1/
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "name": "microservices-example",
  "description": null,
  "builtWith": {
    "buildzr": "0.0.35",
    "k": 4
  },
  "counts": {
    "elements": 13,
    "relationships": 6,
    "views": 1,
    "byType": {
      "Component": 4,
      "Container": 5,
      "Person": 2,
      "SoftwareSystem": 2
    }
  },
  "tags": [
    "Component",
    "Container",
    "Element",
    "Person",
    "Software System"
  ],
  "topLevel": [
    "customer",
    "administrator",
    "e-commerce-system",
    "payment-provider"
  ],
  "viewerUrl": "/",
  "publicUrlConfigured": false,
  "howToAsk": "Element ids are slug paths such as 'e-commerce-system/web-app'; give them in query parameters. Relationships are the explicit ones in the model. A relationship of a descendant counts for its ancestors, so an arrow between two systems is the union of the relationships between their contents. Lists are paged: follow 'next' while 'truncated' is true.",
  "endpoints": {
    "element": "/api/v1/element?id={id}",
    "search": "/api/v1/elements{?q,type,tag,within,limit,cursor}",
    "tree": "/api/v1/tree{?id,depth,limit}",
    "neighbours": "/api/v1/neighbours?id={id}{&direction,depth,type,limit}",
    "path": "/api/v1/path?from={from}&to={to}{&maxHops,limit}",
    "relationships": "/api/v1/relationships{?from,to,edge,tag,limit,cursor}",
    "views": "/api/v1/views{?scope}",
    "view": "/api/v1/view?key={key}"
  },
  "limits": {
    "elements": {
      "default": 50,
      "max": 200
    },
    "relationships": {
      "default": 50,
      "max": 200
    },
    "neighbours": {
      "default": 200,
      "max": 1000
    },
    "tree": {
      "default": 500,
      "max": 1000
    },
    "pathChains": {
      "default": 3,
      "max": 5
    },
    "maxDepth": 4,
    "maxHops": 8,
    "maxQueryLength": 200
  },
  "notes": []
}
```

- `counts`, `tags` and `topLevel` describe the model; `topLevel` lists the ids to start from.
- `endpoints` are URL templates: replace the `{...}` parts. Parameters after `?` or `&` inside braces are optional.
- `limits` are the largest values each parameter accepts (see [Limits](#limits-and-paging)).
- `viewerUrl` is the address of the viewer. It is `null` when the site has no viewer and no `--public-url` was given, and `notes` says so.
- `builtWith` is `null` when the site has no `build.json`.

## Endpoints

All of them are `GET` requests below `<site>/api/v1/`. Element ids go in query parameters.

| Path | Parameters | Answer |
|---|---|---|
| `` (empty) | none | The orientation document. |
| `element` | `id` (required) | One element with all its fields, its `childCount`, the number of relationships in and out (its own, and with its descendants), and its `viewerUrl`. |
| `elements` | `q` (text, at most 200 characters), `type`, `tag` (repeatable: all must match), `within` (an id: only its descendants), `limit` (1 to 200, default 50), `cursor` | Matching elements, best match first: exact name, name starts with, name contains, then description, technology, tags, properties. Not case sensitive. Without `q` the model order is kept. |
| `tree` | `id` (default: the top level), `depth` (1 to 4, default 1), `limit` (1 to 1000, default 500) | The element and its descendants as a nested list. With `id`, `depth=1` shows its children; without it, `depth=1` shows the top level. `children` is `null` where the walk stopped and `[]` for a leaf. |
| `neighbours` | `id` (required), `direction` (`out`, `in` or `both`, default `both`), `depth` (1 to 4, default 1), `type`, `limit` (1 to 1000, default 200) | The relationships that leave (or enter) the element **or any of its descendants**, each with the element at the other end and the hop number. Depth 2 and more continue from those elements the same way. `type` filters the elements at the other end. |
| `path` | `from`, `to` (required), `maxHops` (1 to 8, default 6), `limit` (1 to 5 chains, default 3) | The shortest chains of explicit relationships from `from` (or something inside it) to `to` (or something inside it). All chains have the same, shortest length. `hops` is `null` when there is none within `maxHops`. |
| `relationships` | `from` and/or `to` (ids; each includes what is inside), or `edge` (an arrow id from the viewer, such as `a->b`), `tag` (repeatable), `limit` (1 to 200, default 50), `cursor` | Explicit relationships. With both `from` and `to` this is exactly the rollup the viewer draws for the arrow between the two. |
| `views` | `scope` (an id) | The authored views: `key`, `kind`, `title`, `description`, `scope`, `viewerUrl`. |
| `view` | `key` (required) | One view with the elements it shows and the ids of the relationships drawn in it. |

Unknown parameters are errors, so a typo does not silently give the wrong answer. A parameter that is not repeatable cannot be given twice.

### Endpoint index

The orientation document lists the same endpoints as URL templates. This table is written from that document by `scripts/gen_api_reference.py`, so it follows the code. Do not edit the lines between the two markers; run the script instead. Names in the first column are the keys of `endpoints` in the orientation document (`search` is the path `elements`).

<!-- BEGIN generated: endpoints -->
| Name | Template | Required | Optional | `limit` (default / largest) |
|---|---|---|---|---|
| `element` | `/api/v1/element?id={id}` | `id` | none | none |
| `search` | `/api/v1/elements{?q,type,tag,within,limit,cursor}` | none | `q`, `type`, `tag`, `within`, `limit`, `cursor` | 50 / 200 |
| `tree` | `/api/v1/tree{?id,depth,limit}` | none | `id`, `depth`, `limit` | 500 / 1000 |
| `neighbours` | `/api/v1/neighbours?id={id}{&direction,depth,type,limit}` | `id` | `direction`, `depth`, `type`, `limit` | 200 / 1000 |
| `path` | `/api/v1/path?from={from}&to={to}{&maxHops,limit}` | `from`, `to` | `maxHops`, `limit` | 3 / 5 |
| `relationships` | `/api/v1/relationships{?from,to,edge,tag,limit,cursor}` | none | `from`, `to`, `edge`, `tag`, `limit`, `cursor` | 50 / 200 |
| `views` | `/api/v1/views{?scope}` | none | `scope` | none |
| `view` | `/api/v1/view?key={key}` | `key` | none | none |
<!-- END generated: endpoints -->

### `element`

```http
GET /api/v1/element?id=e-commerce-system/web-app
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "element": {
    "id": "e-commerce-system/web-app",
    "modelId": "4",
    "type": "Container",
    "parent": "e-commerce-system",
    "children": [],
    "name": "Web App",
    "description": null,
    "technology": "React",
    "tags": [
      "Element",
      "Container"
    ],
    "properties": {},
    "url": null,
    "group": "E-Commerce Platform",
    "views": [],
    "childCount": 0,
    "relationships": {
      "own": {
        "in": 2,
        "out": 1
      },
      "withDescendants": {
        "in": 2,
        "out": 1
      }
    },
    "viewerUrl": "/#/m/e-commerce-system?sel=e-commerce-system/web-app"
  }
}
```

`relationships.own` counts the relationships written on the element itself. `withDescendants` counts those that cross the element's border: one end inside it, the other outside.

### `elements`

```http
GET /api/v1/elements?q=mongo
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "total": 1,
  "items": [
    {
      "id": "e-commerce-system/database",
      "name": "Database",
      "type": "Container",
      "parent": "e-commerce-system",
      "description": null,
      "technology": "MongoDB",
      "tags": [
        "Element",
        "Container"
      ],
      "childCount": 0,
      "viewerUrl": "/#/m/e-commerce-system?sel=e-commerce-system/database",
      "matched": "technology"
    }
  ],
  "next": null,
  "truncated": false
}
```

`matched` says which field matched. `total` is the number of matches before paging.

### `tree`

```http
GET /api/v1/tree?id=e-commerce-system&depth=2&limit=7
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "id": "e-commerce-system",
  "depth": 2,
  "items": [
    {
      "id": "e-commerce-system",
      "name": "E-Commerce System",
      "type": "SoftwareSystem",
      "childCount": 5,
      "viewerUrl": "/#/m/e-commerce-system?sel=e-commerce-system",
      "children": [
        {
          "id": "e-commerce-system/web-app",
          "name": "Web App",
          "type": "Container",
          "childCount": 0,
          "viewerUrl": "/#/m/e-commerce-system?sel=e-commerce-system/web-app",
          "children": []
        },
        {
          "id": "e-commerce-system/api-gateway",
          "name": "API Gateway",
          "type": "Container",
          "childCount": 0,
          "viewerUrl": "/#/m/e-commerce-system?sel=e-commerce-system/api-gateway",
          "children": []
        },
        {
          "id": "e-commerce-system/order-service",
          "name": "Order Service",
          "type": "Container",
          "childCount": 2,
          "viewerUrl": "/#/m/e-commerce-system/order-service?sel=e-commerce-system/order-service",
          "children": [
            {
              "id": "e-commerce-system/order-service/order-controller",
              "name": "Order Controller",
              "type": "Component",
              "childCount": 0,
              "viewerUrl": "/#/m/e-commerce-system/order-service?sel=e-commerce-system/order-service/order-controller",
              "children": []
            },
            {
              "id": "e-commerce-system/order-service/order-repository",
              "name": "Order Repository",
              "type": "Component",
              "childCount": 0,
              "viewerUrl": "/#/m/e-commerce-system/order-service?sel=e-commerce-system/order-service/order-repository",
              "children": []
            }
          ]
        },
        {
          "id": "e-commerce-system/inventory-service",
          "name": "Inventory Service",
          "type": "Container",
          "childCount": 2,
          "viewerUrl": "/#/m/e-commerce-system/inventory-service?sel=e-commerce-system/inventory-service",
          "children": null
        }
      ]
    }
  ],
  "next": null,
  "truncated": true
}
```

Here `limit=7` cut the walk after seven elements, so `truncated` is `true`.

### `neighbours`

```http
GET /api/v1/neighbours?id=e-commerce-system/web-app&direction=out&depth=2
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "id": "e-commerce-system/web-app",
  "direction": "out",
  "depth": 2,
  "items": [
    {
      "hop": 1,
      "direction": "out",
      "near": "e-commerce-system/web-app",
      "relationship": {
        "id": "e-commerce-system/web-app->e-commerce-system/api-gateway",
        "source": "e-commerce-system/web-app",
        "destination": "e-commerce-system/api-gateway",
        "description": "Calls",
        "technology": null,
        "tags": [
          "Relationship"
        ],
        "properties": {}
      },
      "element": {
        "id": "e-commerce-system/api-gateway",
        "name": "API Gateway",
        "type": "Container",
        "childCount": 0,
        "viewerUrl": "/#/m/e-commerce-system?sel=e-commerce-system/api-gateway"
      }
    },
    {
      "hop": 2,
      "direction": "out",
      "near": "e-commerce-system/api-gateway",
      "relationship": {
        "id": "e-commerce-system/api-gateway->e-commerce-system/inventory-service",
        "source": "e-commerce-system/api-gateway",
        "destination": "e-commerce-system/inventory-service",
        "description": "Routes to",
        "technology": null,
        "tags": [
          "Relationship"
        ],
        "properties": {}
      },
      "element": {
        "id": "e-commerce-system/inventory-service",
        "name": "Inventory Service",
        "type": "Container",
        "childCount": 2,
        "viewerUrl": "/#/m/e-commerce-system/inventory-service?sel=e-commerce-system/inventory-service"
      }
    }
  ],
  "next": null,
  "truncated": false
}
```

`near` is the element on your side of the relationship: the element you asked about or, for a box with things inside, the thing inside it that holds the relationship.

### `path`

```http
GET /api/v1/path?from=e-commerce-system/web-app&to=e-commerce-system/inventory-service
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "from": "e-commerce-system/web-app",
  "to": "e-commerce-system/inventory-service",
  "maxHops": 6,
  "hops": 2,
  "chains": [
    [
      {
        "rel": "e-commerce-system/web-app->e-commerce-system/api-gateway",
        "from": "e-commerce-system/web-app",
        "to": "e-commerce-system/api-gateway",
        "description": "Calls",
        "technology": null
      },
      {
        "rel": "e-commerce-system/api-gateway->e-commerce-system/inventory-service",
        "from": "e-commerce-system/api-gateway",
        "to": "e-commerce-system/inventory-service",
        "description": "Routes to",
        "technology": null
      }
    ]
  ],
  "next": null,
  "truncated": false
}
```

### `relationships`

```http
GET /api/v1/relationships?from=administrator&to=e-commerce-system
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "from": "administrator",
  "to": "e-commerce-system",
  "edge": null,
  "total": 1,
  "items": [
    {
      "id": "administrator->e-commerce-system/web-app",
      "source": "administrator",
      "destination": "e-commerce-system/web-app",
      "description": "Manages",
      "technology": null,
      "tags": [
        "Relationship"
      ],
      "properties": {}
    }
  ],
  "next": null,
  "truncated": false
}
```

### `views` and `view`

```http
GET /api/v1/views
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "items": [
    {
      "key": "system-context-view-ecommerce",
      "viewKey": "system-context-view-ecommerce",
      "kind": "systemContext",
      "title": "System Context of E-Commerce App",
      "description": "System Context of E-Commerce App",
      "scope": "e-commerce-system",
      "viewerUrl": "/#/v/system-context-view-ecommerce"
    }
  ],
  "next": null,
  "truncated": false
}
```

```http
GET /api/v1/view?key=system-context-view-ecommerce
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "view": {
    "key": "system-context-view-ecommerce",
    "viewKey": "system-context-view-ecommerce",
    "kind": "systemContext",
    "title": "System Context of E-Commerce App",
    "description": "System Context of E-Commerce App",
    "scope": "e-commerce-system",
    "viewerUrl": "/#/v/system-context-view-ecommerce",
    "elements": [
      {
        "id": "customer",
        "name": "Customer",
        "type": "Person",
        "childCount": 0,
        "viewerUrl": "/#/m?sel=customer"
      },
      {
        "id": "administrator",
        "name": "Administrator",
        "type": "Person",
        "childCount": 0,
        "viewerUrl": "/#/m?sel=administrator"
      },
      {
        "id": "e-commerce-system",
        "name": "E-Commerce System",
        "type": "SoftwareSystem",
        "childCount": 5,
        "viewerUrl": "/#/m/e-commerce-system?sel=e-commerce-system"
      },
      {
        "id": "payment-provider",
        "name": "Payment Provider",
        "type": "SoftwareSystem",
        "childCount": 0,
        "viewerUrl": "/#/m?sel=payment-provider"
      }
    ],
    "relationships": [
      "administrator->e-commerce-system/web-app",
      "customer->e-commerce-system/web-app",
      "e-commerce-system/order-service->payment-provider"
    ]
  }
}
```

`relationships` in `view` is `null` when the view's drawing cannot be read.

## The 15 questions

| # | Question | Call |
|---|---|---|
| 1 | What does the model contain at the top level? | `GET api/v1/` (counts and `topLevel`), then `GET api/v1/tree` |
| 2 | What is the e-commerce system made of? | `GET api/v1/tree?id=e-commerce-system&depth=2` |
| 3 | What does the web app depend on, directly and through other things? | `GET api/v1/neighbours?id=e-commerce-system/web-app&direction=out&depth=3` |
| 4 | Which elements talk to the database? | `GET api/v1/neighbours?id=e-commerce-system/database&direction=in` |
| 5 | How does the web app reach the inventory service (shortest chain)? | `GET api/v1/path?from=e-commerce-system/web-app&to=e-commerce-system/inventory-service` |
| 6 | What are the explicit relationships behind the arrow between two boxes? | `GET api/v1/relationships?from=administrator&to=e-commerce-system` |
| 7 | Which elements are tagged Person? | `GET api/v1/elements?tag=Person` |
| 8 | Where is this element shown (which views)? | `GET api/v1/element?id=customer` (field `views`) |
| 9 | Give me a link a person can open for this element. | `GET api/v1/element?id=…` (field `viewerUrl`) |
| 10 | Has the model changed since I last read it? | `GET api/v1/` with `If-None-Match: "<old modelHash>"`: `304` if not |
| 11 | Which people use the e-commerce system? | `GET api/v1/neighbours?id=e-commerce-system&direction=in&type=Person` |
| 12 | What uses MongoDB? | `GET api/v1/elements?q=mongodb` (matches `technology`) |
| 13 | What does this element do, what is it built with, who owns it? | `GET api/v1/element?id=e-commerce-system/order-service` (`description`, `technology`, `properties`) |
| 14 | Which authored views exist, and what does one show? | `GET api/v1/views`, then `GET api/v1/view?key=system-context-view-ecommerce` |
| 15 | What is this arrow I was linked to (`sel=a->b`)? | `GET api/v1/relationships?edge=customer-%3Ee-commerce-system` |

Question 10 in practice: send the `ETag` you got last time.

```http
GET /api/v1/
If-None-Match: "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35"

HTTP/1.0 304 Not Modified
ETag: "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35"
Cache-Control: no-cache
```

Question 15: a viewer link such as `#/m/e-commerce-system?sel=customer->e-commerce-system` names an arrow. Pass the arrow id (`customer->e-commerce-system`, percent-encoded as `customer-%3Ee-commerce-system`) as `edge`. Arrows drawn to the edge of a box that continue outside it (`<child>->port:<outer arrow>`) work too. An explicit relationship id with a description (`a->b:pays`) names exactly that relationship.

## Limits and paging

| Parameter | Smallest | Default | Largest |
|---|---|---|---|
| `limit` of `elements` and `relationships` | 1 | 50 | 200 |
| `limit` of `neighbours` | 1 | 200 | 1000 |
| `limit` of `tree` | 1 | 500 | 1000 |
| `limit` of `path` (chains) | 1 | 3 | 5 |
| `depth` | 1 | 1 | 4 |
| `maxHops` | 1 | 6 | 8 |
| `q` | | | 200 characters |
| any other text parameter | | | 500 characters |

Every list says if it was cut short: `truncated` is `true` and, for `elements` and `relationships`, `next` is the URL of the next page. Follow `next` until `truncated` is `false`. A `cursor` belongs to one model: after a rebuild with a different model an old cursor gets `409` (`cursor-stale`), so a reader never mixes two models. One answer never holds more than about 1 MB of items; if it would, the page ends early and `next` continues from there.

## Errors

Errors are [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) problem details with the content type `application/problem+json`. The members `type`, `title`, `status`, `detail` and `instance` are always there; `code` is a short stable name and `modelHash` is added when the model could be read. `type` is a `urn:buildzr:problem:<code>` name, not a web page.

| Status | `code` | When |
|---|---|---|
| 400 | `bad-parameter` | A missing, unknown, repeated or malformed parameter, a control character, or text that is too long. |
| 400 | `limit-exceeded` | A number outside its range. `detail` names the parameter and the range; `minimum` and `maximum` give it as numbers. |
| 404 | `element-not-found`, `view-not-found` | No such element or view. `candidates` lists up to 5 ids that are close ("did you mean"); for elements `nearest` is the closest existing ancestor. |
| 404 | `unknown-endpoint` | Anything else below `api/v1/`. |
| 405 | `method-not-allowed` | Any method but `GET` and `HEAD`. The answer has `Allow: GET, HEAD`. |
| 409 | `cursor-stale` | A `cursor` from another model. |
| 503 | `model-unavailable` | The site has no readable model (for example while it is being rebuilt). Try again. |

```http
GET /api/v1/element?id=e-commerce-system/web-ap

HTTP/1.0 404
Content-Type: application/problem+json
```

```json
{
  "type": "urn:buildzr:problem:element-not-found",
  "title": "Element not found",
  "status": 404,
  "detail": "No element 'e-commerce-system/web-ap'. Nearest existing ancestor: 'e-commerce-system'. Did you mean: 'e-commerce-system/web-app', 'e-commerce-system', 'e-commerce-system/database', 'e-commerce-system/api-gateway', 'e-commerce-system/order-service'?",
  "instance": "/api/v1/element?id=e-commerce-system/web-ap",
  "code": "element-not-found",
  "parameter": "id",
  "candidates": [
    "e-commerce-system/web-app",
    "e-commerce-system",
    "e-commerce-system/database",
    "e-commerce-system/api-gateway",
    "e-commerce-system/order-service"
  ],
  "nearest": "e-commerce-system",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35"
}
```

Paths in answers are always model ids, never file system paths.

## Caching

Every successful answer has a strong `ETag` that is the quoted `modelHash`, and `Cache-Control: no-cache` (always ask the server, as for the site's other files). Send the tag back in `If-None-Match` and an unchanged model answers `304 Not Modified` with no body. The tag identifies the model, not the query, so use it only for the URL you got it from. Errors have no `ETag`. When the site is rebuilt, the server notices the new `data/index.json` on the next request and serves the new model without a restart.

## Browsers and CORS

By default the API sends **no** CORS headers, so a web page opened from another site cannot read it through the visitor's browser. A model inside a company network should not be readable by any page a staff member happens to open. To allow one tool, name its origin (scheme, host and port, no path), once per origin:

```text
buildzr serve --cors-origin https://tool.example.com --cors-origin http://localhost:3000
```

Only a request whose `Origin` header is in the list gets `Access-Control-Allow-Origin: <that origin>` and `Vary: Origin`. There is no wildcard, and `OPTIONS` requests are not handled, so only "simple" `GET` requests work from a browser.

## Links to the viewer: `--public-url`

Every element in an answer has a `viewerUrl`, a link a person can open to see that element. The link follows the viewer's [hash routes](viewer-hash-routes.md): an element with things inside opens expanded, and a leaf opens inside its parent with itself selected. Element types the viewer does not draw have `viewerUrl: null`.

Without `--public-url` the links are paths on the same server (`/#/m/e-commerce-system?sel=e-commerce-system/web-app`), which is right when you are reading from the server itself. Behind a proxy or on a shared host, tell `serve` the address readers use:

```text
buildzr serve --public-url https://models.example.com/pr/42/
```

Links, `endpoints` and `next` are then absolute: `https://models.example.com/pr/42/#/m/e-commerce-system?sel=...`. The address is never guessed from request headers. A trailing `/` is dropped; the value must start with `http://` or `https://` and have no `?` or `#`.

A site built with `viewer: false` has data only. `buildzr serve` still starts and the API works. Its `viewerUrl` links are `null` (and `notes` in the orientation document says so) unless `--public-url` is given: the links then point at that address, where the viewer is expected to be served from.

## `llms.txt`

`GET /llms.txt` returns a short plain-text page, made from the orientation document (under 2 KB), that says what the site is and links to `api/v1/` and to every endpoint, so tools that look for that file find the API.

## What the API will not do

- It never writes: other methods get `405`, and the server does not create or change files.
- It only reads the model file and the scene files named in the site's `data/index.json`, and only inside the site's `data/` folder. A name in `index.json` that points elsewhere makes the model unavailable instead of being read.
- Deployment nodes and the drawing's geometry are not in the answers. Neither is a comparison between two builds.
- Version: all paths are below `api/v1/`. New fields may appear in answers without a version change; a change that removes or renames something would arrive as `api/v2/`.
