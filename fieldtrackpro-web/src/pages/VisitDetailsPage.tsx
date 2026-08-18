import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, Image as ImageIcon, MapPin, Upload, LogOut, FileSignature, ClipboardList, Eye, PlayCircle, PackagePlus } from 'lucide-react';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../api/client';
import { AccountSummary, Customer, FormSubmission, GeoVerificationLog, Visit, VisitMedia, VisitSignature, VisitStatus } from '../types';
import { MediaThumbnail } from '../components/ui/MediaThumbnail';
import { SignatureThumbnail } from '../components/ui/SignatureThumbnail';
import { AccountSummaryCard } from '../components/ui/AccountSummaryCard';
import { CollectPaymentModal } from '../components/ui/CollectPaymentModal';

export const VisitDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const [visit, setVisit] = useState<Visit | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [geoLogs, setGeoLogs] = useState<GeoVerificationLog[]>([]);
  const [mediaList, setMediaList] = useState<VisitMedia[]>([]);
  const [signatures, setSignatures] = useState<VisitSignature[]>([]);
  const currentSignatures = signatures.filter((sig) => sig.superseded_at === null);
  const [formSubmissions, setFormSubmissions] = useState<FormSubmission[]>([]);
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [isCollectModalOpen, setIsCollectModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Geo action state. Latitude/longitude/accuracy are intentionally never
  // editable by the user (see useMyLocation's comment below) - they exist
  // only to display whatever the browser's GPS just reported. capturedAt
  // records when that reading happened, sent to the server so it can reject
  // check-ins built from a stale/replayed fix; hasRealCapture gates
  // submission so a check-in can never fire without a genuine GPS read.
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [accuracy, setAccuracy] = useState('10');
  const [capturedAt, setCapturedAt] = useState<string | null>(null);
  const [hasRealCapture, setHasRealCapture] = useState(false);
  const [geoStatus, setGeoStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [isSubmittingGeo, setIsSubmittingGeo] = useState(false);
  const [isLocating, setIsLocating] = useState(false);

  // Media upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  // Order capture state (P2-B) - reuses the media upload pipeline with is_order=true.
  const [orderFile, setOrderFile] = useState<File | null>(null);
  const [orderNote, setOrderNote] = useState('');
  const [orderStatus, setOrderStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [isCapturingOrder, setIsCapturingOrder] = useState(false);

  const reload = useCallback(async () => {
    if (!id) return;
    setError(null);
    try {
      const visitData = await apiClient.getVisitById(id);
      setVisit(visitData);

      const [logs, media, cust, sigs, submissions, acct] = await Promise.all([
        apiClient.getVisitGeoLogs(id).catch(() => [] as GeoVerificationLog[]),
        apiClient.getVisitMedia(id).catch(() => [] as VisitMedia[]),
        apiClient.getCustomerById(visitData.customer_id).catch(() => null),
        apiClient.getVisitSignatures(id).catch(() => [] as VisitSignature[]),
        // Scoped to this visit only - the form(s) actually required for it
        // are already on visitData.required_form_id, not a global catalog.
        apiClient.getFormSubmissions({ visit_id: id }).catch(() => [] as FormSubmission[]),
        apiClient.getCustomerAccount(visitData.customer_id).catch(() => null),
      ]);
      setGeoLogs(logs);
      setMediaList(media);
      setCustomer(cust);
      setSignatures(sigs);
      setFormSubmissions(submissions);
      setAccount(acct);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load visit details');
    }
  }, [id]);

  useEffect(() => {
    setIsLoading(true);
    reload().finally(() => setIsLoading(false));
  }, [reload]);

  /**
   * Read the device's real position.
   *
   * The coordinate fields start empty and are filled from the browser
   * Geolocation API. They were previously pre-populated with fixed Bengaluru
   * coordinates, which invited a check-in that had nothing to do with where
   * the user actually was. The fields are also read-only (see the JSX below)
   * - this is the ONLY place lat/lng/accuracy/capturedAt are ever set, so a
   * check-in can never be built from hand-typed coordinates.
   */
  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setGeoStatus({ ok: false, text: 'This browser does not provide location services.' });
      return;
    }
    setIsLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(String(pos.coords.latitude));
        setLng(String(pos.coords.longitude));
        if (pos.coords.accuracy) setAccuracy(String(Math.round(pos.coords.accuracy)));
        setCapturedAt(new Date().toISOString());
        setHasRealCapture(true);
        setGeoStatus(null);
        setIsLocating(false);
      },
      (err) => {
        setGeoStatus({
          ok: false,
          text:
            err.code === err.PERMISSION_DENIED
              ? 'Location permission denied. Enable it to check in.'
              : 'Could not obtain a GPS fix. Move to open sky and retry.',
        });
        setIsLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  };

  const submitGeoAction = async (action: 'check-in' | 'check-out') => {
    if (!id) return;
    if (!hasRealCapture || !capturedAt) {
      setGeoStatus({ ok: false, text: 'Capture your location before continuing.' });
      return;
    }
    const latitude = parseFloat(lat);
    const longitude = parseFloat(lng);
    if (Number.isNaN(latitude) || Number.isNaN(longitude)) {
      setGeoStatus({ ok: false, text: 'Capture your location before continuing.' });
      return;
    }
    setGeoStatus(null);
    setIsSubmittingGeo(true);
    try {
      const payload = {
        latitude,
        longitude,
        accuracy_m: accuracy ? parseFloat(accuracy) : undefined,
        is_mock_location: false,
        captured_at: capturedAt,
      };
      if (action === 'check-in') {
        // FT-037: an idempotency key makes a retried check-in safe.
        await apiClient.checkIn(id, { ...payload, idempotency_key: crypto.randomUUID() });
        setGeoStatus({ ok: true, text: 'Check-in verified successfully.' });
      } else {
        await apiClient.checkOut(id, { ...payload, idempotency_key: crypto.randomUUID() });
        setGeoStatus({ ok: true, text: 'Check-out verified. Visit completed.' });
      }
      setHasRealCapture(false);
      await reload();
    } catch (err) {
      setGeoStatus({
        ok: false,
        text: err instanceof Error ? err.message : 'Verification rejected',
      });
      await reload(); // a failed attempt still creates an audit record
    } finally {
      setIsSubmittingGeo(false);
    }
  };

  const handleUploadMedia = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !selectedFile) return;
    setUploadStatus(null);
    setIsUploading(true);
    try {
      await apiClient.uploadMedia(id, selectedFile);
      setUploadStatus({ ok: true, text: 'Attachment uploaded successfully.' });
      setSelectedFile(null);
      await reload();
    } catch (err) {
      setUploadStatus({
        ok: false,
        text: err instanceof Error ? err.message : 'Upload failed',
      });
    } finally {
      setIsUploading(false);
    }
  };

  const handleCaptureOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !orderFile) return;
    setOrderStatus(null);
    setIsCapturingOrder(true);
    try {
      await apiClient.uploadOrderCapture(id, orderFile, orderNote.trim() || undefined);
      setOrderStatus({ ok: true, text: 'Order captured successfully.' });
      setOrderFile(null);
      setOrderNote('');
      await reload();
    } catch (err) {
      setOrderStatus({ ok: false, text: err instanceof Error ? err.message : 'Order capture failed' });
    } finally {
      setIsCapturingOrder(false);
    }
  };

  const handleForceStatus = async (status: VisitStatus) => {
    if (!id) return;
    try {
      await apiClient.updateVisitStatus(id, status, 'Admin override from visit details');
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update status');
    }
  };

  if (isLoading) {
    return (
      <div className="py-space-12 text-center text-on-surface-variant font-caption">
        Loading visit telemetry details...
      </div>
    );
  }

  if (error || !visit) {
    return (
      <div className="space-y-space-4 font-body-md text-on-surface">
        <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate('/visits')}>
          Back to Visits Schedule
        </Button>
        <ErrorBanner message={error || 'Visit record not found'} onRetry={() => void reload()} />
      </div>
    );
  }

  const canCheckIn = visit.status === 'PENDING' || visit.status === 'FLAGGED';
  const canCheckOut = visit.status === 'IN_PROGRESS';
  const failureCount = geoLogs.filter((l) => !l.is_valid).length;

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate('/visits')}>
        Back to Visits Schedule
      </Button>

      <Card variant="default">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-4 border-b border-surface-container-highest pb-space-4 mb-space-4">
          <div>
            <span className="font-caption text-xs text-on-surface-variant uppercase tracking-wider block mb-1">
              VISIT RECORD #{visit.id.substring(0, 8)}
            </span>
            <h1 className="font-headline-lg text-2xl font-bold text-primary">
              {visit.customer_name || customer?.name || `Customer #${visit.customer_id.substring(0, 8)}`}
            </h1>
            {(visit.customer_address || customer?.address) && (
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                {visit.customer_address || customer?.address}
              </p>
            )}
            {visit.employee_name && (
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                <span className="font-semibold">Assignee:</span> {visit.employee_name}
              </p>
            )}
            {(visit.territory_name || visit.area_name) && (
              <p className="font-caption text-xs text-on-surface-variant mt-0.5">
                <span className="font-semibold">Zone/Area:</span> {[visit.territory_name, visit.area_name].filter(Boolean).join(' / ')}
              </p>
            )}
          </div>
          <StatusBadge status={visit.status} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-space-4 text-body-md">
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">
              Scheduled
            </p>
            <p className="font-body-md text-sm text-on-surface font-medium">
              {new Date(visit.scheduled_at).toLocaleString()}
            </p>
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">
              Check-In
            </p>
            <p className="font-body-md text-sm text-on-surface font-medium">
              {visit.check_in_at ? new Date(visit.check_in_at).toLocaleString() : 'Not checked in'}
            </p>
            {visit.check_in_received_at && visit.check_in_at && visit.check_in_received_at !== visit.check_in_at && (
              <p className="font-caption text-[11px] text-on-surface-variant mt-0.5">
                Synced: {new Date(visit.check_in_received_at).toLocaleTimeString()}
              </p>
            )}
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">
              Check-Out
            </p>
            <p className="font-body-md text-sm text-on-surface font-medium">
              {visit.check_out_at ? new Date(visit.check_out_at).toLocaleString() : 'Not checked out'}
            </p>
            {visit.check_out_received_at && visit.check_out_at && visit.check_out_received_at !== visit.check_out_at && (
              <p className="font-caption text-[11px] text-on-surface-variant mt-0.5">
                Synced: {new Date(visit.check_out_received_at).toLocaleTimeString()}
              </p>
            )}
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">
              Verification Failures
            </p>
            <p
              className={`font-headline-sm text-sm ${
                failureCount > 0
                  ? 'text-secondary font-bold bg-secondary-fixed/40 px-2 py-0.5 rounded inline-block'
                  : 'text-primary font-bold'
              }`}
            >
              {failureCount} attempt{failureCount === 1 ? '' : 's'}
            </p>
          </div>
        </div>

        {/* FT-020: admin override, previously unreachable from the UI. */}
        {isAdmin && visit.status !== 'COMPLETED' && visit.status !== 'MISSED' && (
          <div className="mt-space-4 pt-space-4 border-t border-surface-container-highest flex flex-wrap items-center gap-space-3">
            <span className="font-label-md text-xs uppercase text-on-surface-variant font-semibold">
              Admin override
            </span>
            <Button variant="outline" size="sm" onClick={() => void handleForceStatus('MISSED')}>
              Mark Missed
            </Button>
            <Button variant="outline" size="sm" onClick={() => void handleForceStatus('COMPLETED')}>
              Approve As Completed
            </Button>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-6">
        {/* Geo verification */}
        <Card variant="default" className="space-y-space-4">
          <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
            <ShieldCheck className="w-5 h-5 text-primary" />
            <h3 className="font-headline-sm text-base font-bold text-primary">
              GPS Verification &amp; Check-In ({geoLogs.length})
            </h3>
          </div>

          {canCheckIn || canCheckOut ? (
            <div className="p-space-4 bg-surface-container-low border border-outline-variant rounded-xl space-y-space-3">
              <p className="font-headline-sm text-sm text-primary font-bold flex items-center gap-space-1.5">
                <MapPin className="w-4 h-4 text-secondary-container" />
                {canCheckIn ? 'Execute Geo Check-In' : 'Complete Visit (Check-Out)'}
              </p>

              {geoStatus && (
                <div
                  className={`p-space-2.5 rounded-lg border font-body-md text-xs ${
                    geoStatus.ok
                      ? 'bg-primary-container text-on-primary-container border-primary-container'
                      : 'bg-error-container text-on-error-container border-error'
                  }`}
                >
                  {geoStatus.text}
                </div>
              )}

              <Button
                type="button"
                variant="outline"
                size="sm"
                icon={MapPin}
                className="w-full"
                onClick={useMyLocation}
                isLoading={isLocating}
              >
                Use My Current Location
              </Button>

              <div className="grid grid-cols-3 gap-space-2">
                {/* Read-only display of whatever "Use My Current Location"
                    just captured - these must never be user-editable, or a
                    rep could type in an outlet's coordinates without
                    actually being there. */}
                <Input
                  label="LATITUDE"
                  type="number"
                  step="any"
                  value={lat}
                  readOnly
                  placeholder="—"
                />
                <Input
                  label="LONGITUDE"
                  type="number"
                  step="any"
                  value={lng}
                  readOnly
                  placeholder="—"
                />
                <Input
                  label="ACCURACY (M)"
                  type="number"
                  step="any"
                  value={accuracy}
                  readOnly
                />
              </div>

              {canCheckIn && (
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  className="w-full"
                  isLoading={isSubmittingGeo}
                  disabled={!hasRealCapture}
                  onClick={() => void submitGeoAction('check-in')}
                >
                  Perform Check-In
                </Button>
              )}

              {/* FT-039: check-out had no control at all, so a visit could
                  never reach COMPLETED from the web client. */}
              {canCheckOut && (
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  icon={LogOut}
                  className="w-full"
                  isLoading={isSubmittingGeo}
                  disabled={!hasRealCapture}
                  onClick={() => void submitGeoAction('check-out')}
                >
                  Perform Check-Out
                </Button>
              )}
            </div>
          ) : (
            <p className="font-caption text-xs text-on-surface-variant p-space-3 bg-surface-container-low border border-outline-variant rounded-xl">
              {visit.status === 'COMPLETED'
                ? 'This visit is complete. No further geo actions are available.'
                : 'This visit is closed. No further geo actions are available.'}
            </p>
          )}

          {geoLogs.length === 0 ? (
            <p className="font-caption text-xs text-on-surface-variant py-space-4 text-center">
              No geo check attempts recorded for this visit.
            </p>
          ) : (
            <div className="space-y-space-3 max-h-64 overflow-y-auto pr-space-1">
              {geoLogs.map((log) => (
                <div
                  key={log.id}
                  className="p-space-3 bg-surface-container-low border border-outline-variant rounded-lg font-body-md text-xs space-y-space-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-headline-sm text-primary font-bold">
                      {log.verification_type.replace('_', '-')}
                    </span>
                    <StatusBadge status={log.is_valid ? 'VALID' : 'INVALID'} size="sm" />
                  </div>
                  {log.latitude !== null && log.longitude !== null && (
                    <p className="font-caption text-on-surface-variant font-mono">
                      Coords: {log.latitude.toFixed(6)}, {log.longitude.toFixed(6)}
                    </p>
                  )}
                  <p className="font-caption text-on-surface-variant">
                    Distance to target: {Math.round(log.distance_from_customer_m)}m
                  </p>
                  <p className="font-caption text-on-surface-variant">
                    {new Date(log.attempted_at).toLocaleString()}
                  </p>
                  {log.failure_reason && (
                    <p className="text-error font-semibold">Reason: {log.failure_reason}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Media (generic attachments - order captures have their own section below) */}
        <Card variant="default" className="space-y-space-4">
          <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
            <ImageIcon className="w-5 h-5 text-primary" />
            <h3 className="font-headline-sm text-base font-bold text-primary">
              Attached Media &amp; Files ({mediaList.filter((m) => m.media_type !== 'ORDER').length})
            </h3>
          </div>

          <form
            onSubmit={handleUploadMedia}
            className="p-space-4 bg-surface-container-low border border-outline-variant rounded-xl space-y-space-3"
          >
            <p className="font-headline-sm text-sm text-primary font-bold flex items-center gap-space-1.5">
              <Upload className="w-4 h-4 text-secondary-container" /> Upload Visit Attachment
            </p>
            {uploadStatus && (
              <div
                className={`p-space-2.5 rounded-lg border font-body-md text-xs ${
                  uploadStatus.ok
                    ? 'bg-primary-container text-on-primary-container border-primary-container'
                    : 'bg-error-container text-on-error-container border-error'
                }`}
              >
                {uploadStatus.text}
              </div>
            )}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              aria-label="Select attachment"
              onChange={(e) => setSelectedFile(e.target.files ? e.target.files[0] : null)}
              className="w-full bg-surface border border-outline-variant rounded-lg px-space-3 py-space-2 text-on-surface font-body-md text-xs file:bg-surface-container file:text-on-surface file:border-0 file:rounded file:px-space-2 file:py-space-1 file:mr-space-2 cursor-pointer"
            />
            <p className="font-caption text-xs text-on-surface-variant">
              JPEG, PNG, WEBP or PDF. Maximum 10 MB.
            </p>
            <Button
              type="submit"
              variant="secondary"
              size="md"
              className="w-full"
              disabled={!selectedFile}
              isLoading={isUploading}
            >
              Upload Attachment
            </Button>
          </form>

          {mediaList.filter((m) => m.media_type !== 'ORDER').length === 0 ? (
            <p className="font-caption text-xs text-on-surface-variant py-space-4 text-center">
              No media attachments uploaded for this visit.
            </p>
          ) : (
            <div className="space-y-space-3 max-h-72 overflow-y-auto pr-space-1">
              {mediaList.filter((m) => m.media_type !== 'ORDER').map((media) => (
                <MediaThumbnail
                  key={media.id}
                  media={media}
                  onDeleted={() => void reload()}
                  canDelete
                />
              ))}
            </div>
          )}
        </Card>

        {/* Order capture (P2-B) - a photographed order diary note, tied to this visit/outlet. */}
        <Card variant="default" className="space-y-space-4">
          <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
            <PackagePlus className="w-5 h-5 text-primary" />
            <h3 className="font-headline-sm text-base font-bold text-primary">
              Orders ({mediaList.filter((m) => m.media_type === 'ORDER').length})
            </h3>
          </div>

          <form
            onSubmit={handleCaptureOrder}
            className="p-space-4 bg-surface-container-low border border-outline-variant rounded-xl space-y-space-3"
          >
            <p className="font-headline-sm text-sm text-primary font-bold flex items-center gap-space-1.5">
              <PackagePlus className="w-4 h-4 text-secondary-container" /> Capture Order
            </p>
            {orderStatus && (
              <div
                className={`p-space-2.5 rounded-lg border font-body-md text-xs ${
                  orderStatus.ok
                    ? 'bg-primary-container text-on-primary-container border-primary-container'
                    : 'bg-error-container text-on-error-container border-error'
                }`}
              >
                {orderStatus.text}
              </div>
            )}
            <textarea
              value={orderNote}
              onChange={(e) => setOrderNote(e.target.value)}
              placeholder="Order diary note - e.g. 5x Usha fans, 2x Singer mixers"
              rows={2}
              className="w-full bg-surface border border-outline-variant rounded-lg px-space-3 py-space-2 text-on-surface font-body-md text-sm placeholder:text-outline focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all resize-vertical"
            />
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              aria-label="Order photo"
              onChange={(e) => setOrderFile(e.target.files ? e.target.files[0] : null)}
              className="w-full bg-surface border border-outline-variant rounded-lg px-space-3 py-space-2 text-on-surface font-body-md text-xs file:bg-surface-container file:text-on-surface file:border-0 file:rounded file:px-space-2 file:py-space-1 file:mr-space-2 cursor-pointer"
            />
            <Button
              type="submit"
              variant="secondary"
              size="md"
              className="w-full"
              icon={PackagePlus}
              disabled={!orderFile}
              isLoading={isCapturingOrder}
            >
              Save Order
            </Button>
          </form>

          {mediaList.filter((m) => m.media_type === 'ORDER').length === 0 ? (
            <p className="font-caption text-xs text-on-surface-variant py-space-4 text-center">
              No orders captured for this visit yet.
            </p>
          ) : (
            <div className="space-y-space-3 max-h-72 overflow-y-auto pr-space-1">
              {mediaList.filter((m) => m.media_type === 'ORDER').map((media) => (
                <MediaThumbnail key={media.id} media={media} onDeleted={() => void reload()} canDelete />
              ))}
            </div>
          )}
        </Card>

        {/* P1: Outlet Account - outstanding/aging/history + Collect Payment, right in the visit workflow */}
        {account && (
          <AccountSummaryCard
            account={account}
            onCollectPayment={visit?.status === 'IN_PROGRESS' ? () => setIsCollectModalOpen(true) : undefined}
          />
        )}

        {/* Required Form - the ONE form template assigned to this visit
            (Forms-as-a-Visit-workflow fix). Never a global list of every
            published template - that was the bug: any employee opening any
            visit used to see the same catalog of every form in the system. */}
        <Card variant="default" className="space-y-space-4">
          <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
            <ClipboardList className="w-5 h-5 text-primary" />
            <h3 className="font-headline-sm text-base font-bold text-primary">Required Form</h3>
          </div>

          {!visit?.required_form_id ? (
            <p className="font-caption text-xs text-on-surface-variant py-space-4 text-center">
              No form required for this visit.
            </p>
          ) : (
            (() => {
              const submission = formSubmissions.find((s) => s.form_id === visit.required_form_id);
              return (
                <div className="p-space-3.5 bg-surface-container-low border border-outline-variant rounded-lg flex items-center justify-between gap-space-3">
                  <div className="min-w-0">
                    <p className="font-headline-sm text-sm text-primary font-bold truncate">{visit.required_form_name}</p>
                    <p className="font-caption text-xs text-on-surface-variant">
                      Status: {submission ? (submission.status === 'SUBMITTED' ? 'Submitted' : 'Draft') : 'Not Started'}
                      {submission?.submitted_at ? ` · ${new Date(submission.submitted_at).toLocaleString()}` : ''}
                    </p>
                    {visit.required_form_status === 'ARCHIVED' && (
                      <p className="font-caption text-xs text-secondary mt-0.5">This form has since been archived.</p>
                    )}
                  </div>
                  <div className="flex items-center gap-space-2 shrink-0">
                    {submission && <StatusBadge status={submission.status} size="sm" />}
                    {submission?.status === 'SUBMITTED' ? (
                      <Button variant="outline" size="sm" icon={Eye} onClick={() => navigate(`/visits/${id}/forms/${visit.required_form_id}`)}>
                        View
                      </Button>
                    ) : (
                      <Button variant="secondary" size="sm" icon={PlayCircle} onClick={() => navigate(`/visits/${id}/forms/${visit.required_form_id}`)}>
                        {submission ? 'Continue' : 'Start Form'}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })()
          )}
        </Card>

        {/* Signatures - only the current (non-superseded) capture per type is
            shown here; a replaced capture is kept server-side as an audit
            trail, not as a second visible entry. */}
        {currentSignatures.length > 0 && (
          <Card variant="default" className="space-y-space-4">
            <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
              <FileSignature className="w-5 h-5 text-primary" />
              <h3 className="font-headline-sm text-base font-bold text-primary">
                Signatures &amp; Acknowledgements ({currentSignatures.length})
              </h3>
            </div>
            <div className="space-y-space-3">
              {currentSignatures.map((sig) => (
                <SignatureThumbnail key={sig.id} signature={sig} />
              ))}
            </div>
          </Card>
        )}
      </div>

      {id && (
        <CollectPaymentModal
          isOpen={isCollectModalOpen}
          onClose={() => setIsCollectModalOpen(false)}
          visitId={id}
          outstandingInvoices={account?.recent_invoices?.filter((inv) => Number(inv.remaining_amount) > 0) ?? []}
          onCollected={() => void reload()}
        />
      )}
    </div>
  );
};
