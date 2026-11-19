from ..services import drills
class TrailsController:
    list=staticmethod(drills.list_trails)
    create=staticmethod(drills.create_trail)
    get=staticmethod(drills.get_trail)
    batch=staticmethod(drills.accept_batch)
    solve=staticmethod(drills.solve_trail)
    coverage=staticmethod(drills.coverage_report)
