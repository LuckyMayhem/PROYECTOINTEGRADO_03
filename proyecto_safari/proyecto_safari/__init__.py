try:
    import MySQLdb
except ImportError:
    try:
        import pymysql
        # Integración de PyMySQL como fallback si no está instalado mysqlclient nativo
        pymysql.install_as_MySQLdb()
    except ImportError:
        pass
