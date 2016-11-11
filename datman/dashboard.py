"""Functions for interacting with the dashboard database"""
from __future__ import absolute_import
import logging
import dashboard
#from dashboard.models import Study, Session, Scan, ScanType
import datman.scanid
import datman.utils
from datetime import datetime

logger = logging.getLogger(__name__)
db = dashboard.db
Study = dashboard.models.Study
Session = dashboard.models.Session
Scan = dashboard.models.Scan
ScanType = dashboard.models.ScanType

class DashboardException(Exception):
    pass


class dashboard(object):
    study = None
    def __init__(self, study):
        self.set_study(study)

    def set_study(self, study):
        """Sets the object study"""
        qry = Study.query.filter(Study.nickname == study)
        if qry.count() < 1:
            logger.error('Study:{} not found in dashboard')
            raise DashboardException("Study not found")
        self.study = qry.first()

    def get_add_session(self, session_name, date=None, create=False):
        """Returns a session object, creates one if doesnt exist and create
        is True"""
        if not self.study:
            logger.error('Study not set')
            return DashboardException('Study not set')

        try:
            ident = datman.scanid.parse(session_name)
        except datman.scanid.ParseException:
            logger.error('Invalid session:{}'.format(session_name))
            return DashboardException('Invalid session name:{}'
                                      .format(session_name))

        dashboard_site = [site for site
                          in self.study.sites
                          if site.name == ident.site]
        if not dashboard_site:
            logger.error('Invalid site:{} in session:{}'
                         .format(ident.site, session_name))
            return(DashboardException('Invalid site'))

        if date:
            try:
                date = datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                logger.error('Invalid date:{} for session:{}'
                             .format(date, session_name))
                return(DashboardException('Invalid date'))

        qry = Session.query.filter(Session.study == self.study).filter(Session.name == session_name)

        if qry.count() == 1:
            logger.info('Found session:{}'.format(session_name))
            dashboard_session = qry.first()
            if date:
                if not datetime.strftime(date, '%Y-%m-%d') == datetime.strftime(dashboard_session.date, '%Y-%m-%d'):
                    logger.debug('Updating date for session:{}'
                                 .format(session_name))
                    dashboard_session.date = date
                    db.session.add(dashboard_session)

        elif qry.count() < 1:
            logger.info("Session:{} doesnt exist".format(session_name))
            if create:
                logger.debug('Creating session:{}'.format(session_name))
                dashboard_session = Session()
                dashboard_session.site = dashboard_site[0]
                dashboard_session.name = session_name
                dashboard_session.study = self.study
                dashboard_session.date = date
                if datman.scanid.is_phantom(session_name):
                    dashboard_session.is_phantom = True
                db.session.add(dashboard_session)
            else:
                return None
        # check for cheklist comments:
        try:
            cl_comment = datman.utils.check_checklist(session_name,
                                                      study=self.study.nickname)
        except ValueError as e:
            logger.error('Failed to check checklist for session:'
                         '{} with error:{}'.format(session_name, str(e)))
        if not cl_comment == dashboard_session.cl_comment:
            dashboard_session.cl_comment = cl_comment
        try:
            db.session.commit()
        except Exception as e:
            logger.error('An error occured adding session:{} to the database'
                         'Error:{}'
                         .format(session_name, str(e)))
            return None
        return dashboard_session

    def get_add_scan(self, scan_name, create=False):
        """Returns a scan object, creates one if doesnt exist and create
        is True"""
        if not self.study:
            logger.error('Study not set')
            return DashboardException('Study not set')

        try:
            ident, tag, series, desc = datman.scanid.parse_filename(scan_name)
        except datman.scanid.ParseException as e:
            logger.error('Invalid scan name:{}'.format(scan_name))
            raise DashboardException('Invalid scan_name')
        scan_id = '{}_{}_{}'.format(str(ident), tag, series)
        session_name = ident.get_full_subjectid_with_timepoint()

        qry = db.session.query(Scan) \
                        .join(Session) \
                        .join(Study, Session.study) \
                        .filter(Session.name == session_name) \
                        .filter(Study.nickname == self.study.nickname) \
                        .filter(Scan.name == scan_id)

        if qry.count() == 1:
            logger.debug('Found scan:{} in database'.format(scan_name))
            dashboard_scan = qry.first()

        elif qry.count() > 1:
            logger.error('Scan:{} was not uniquely identified in the database'
                         .format(scan_name))
            raise DashboardException('Scan not unique')

        else:
            if not create:
                logger.info('Scan:{} not found but create is false, skipping'
                            .format(scan_name))
                return
            try:
                dashboard_session = self.get_add_session(session_name,
                                                         create=create)
            except DashboardException as e:
                raise(e)

            try:
                dashboard_scantype = self.get_scantype(tag)
            except DashboardException as e:
                raise(e)

            if not dashboard_scantype in self.study.scantypes:
                logger.error('Scantype:{} not valid for study:{}'
                             .format(dashboard_scantype.name,
                                     self.study.nickname))
                raise DashboardException('Invalid scantype')

            dashboard_scan = Scan()
            dashboard_scan.session = dashboard_session
            dashboard_scan.name = scan_id
            dashboard_scan.series_number = series
            dashboard_scan.scantype = dashboard_scantype
            dashboard_scan.description = desc

            db.session.add(dashboard_scan)
        # finally check the blacklist
        try:
            bl_comment = datman.utils.check_blacklist(scan_name,
                                                      study=self.study.nickname)
        except ValueError as e:
            logger.error('Failed to check blacklist for scan:{} with error:{}'
                         .format(scan_name, str(e)))

        if not bl_comment == dashboard_scan.bl_comment:
            dashboard_scan.bl_comment = bl_comment
        try:
            db.session.commit()
        except Exception as e:
            logger.error('An error occured adding scan:{} to the db.Error:{}'
                         .format(scan_name, str(e)))
        return(dashboard_scan)


    def get_scantype(self, scantype):
        qry = ScanType.query.filter(ScanType.name == scantype)
        if qry.count() < 1:
            logger.error('Scantype:{} not found in database'.format(scantype))
            raise DashboardException('Invalid scantype')
        else:
            return qry.first()
