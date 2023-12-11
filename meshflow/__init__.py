def classFactory(iface):
    from .plugin import MeshFlowPlugin

    return MeshFlowPlugin(iface)
