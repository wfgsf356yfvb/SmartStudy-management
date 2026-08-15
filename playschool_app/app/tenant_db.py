from mysql.connector import pooling, Error
from collections import OrderedDict
from config import Config

# LRU cache for connection pools keyed by database name
_MAX_POOLS = 12
_pools = OrderedDict()

_base_config = {
    'host': Config.MYSQL_HOST,
    'user': Config.MYSQL_USER,
    'password': Config.MYSQL_PASSWORD,
    'port': Config.MYSQL_PORT,
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'autocommit': False,
}


def _create_pool_for(db_name):
    cfg = dict(_base_config)
    cfg['database'] = db_name
    # pool name must be unique
    pool_name = f"playschool_pool_{db_name}"
    pool = pooling.MySQLConnectionPool(
        pool_name=pool_name,
        pool_size=3,
        pool_reset_session=True,
        **cfg
    )
    return pool


def get_pool(db_name):
    db_name = str(db_name)
    if db_name in _pools:
        # move to end -> most recently used
        _pools.move_to_end(db_name)
        return _pools[db_name]
    # create
    pool = _create_pool_for(db_name)
    _pools[db_name] = pool
    # evict LRU if too many
    if len(_pools) > _MAX_POOLS:
        _pools.popitem(last=False)
    return pool


def get_connection_for_tenant(subdomain):
    """Return a connection object for the given tenant subdomain.
    Tenant DB name convention: playschool_tenant_{subdomain}
    """
    db_name = f"playschool_tenant_{subdomain}"
    pool = get_pool(db_name)
    return pool.get_connection()
