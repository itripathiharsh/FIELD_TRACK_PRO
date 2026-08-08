import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, Image as ImageIcon, MapPin, Upload, LogOut } from 'lucide-react';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../api/client';
import { Customer, GeoVerificationLog, Visit, VisitMedia, VisitStatus } from '../types';
import { MediaThumbnail } from '../components/ui/MediaThumbnail';

export const VisitDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const [visit, setVisit] = useState<Visit | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [geoLogs, setGeoLogs] = useState<GeoVerificationLog[]>([]);
  const [mediaList, setMediaList] = useState<VisitMedia[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Geo action state
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [accuracy, setAccuracy] = useState('10');
  const [geoStatus, setGeoStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [isSubmittingGeo, setIsSubmittingGeo] = useState(false);
  const [isLocating, setIsLocating] = useState(false);

  // Media upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const reload = useCallback(async () => {
    if (!id) return;
    setError(null);
    try {
      const visitData = await apiClient.getVisitById(id);
      setVisit(visitData);

      const [logs, media, cust] = await Promise.all([
        apiClient.getVisitGeoLogs(id).catch(() => [] as GeoVerificationLog[]),
        apiClient.getVisitMedia(id).catch(() => [] as VisitMedia[]),
        apiClient.getCustomerById(visitData.customer_id).catch(() => null),
      ]);
      setGeoLogs(logs);
      setMediaList(media);
      setCustomer(cust);
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
   * the user actually was.
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
      };
      if (action === 'check-in') {
        // FT-037: an idempotency key makes a retried check-in safe.
        await apiClient.checkIn(id, { ...payload, idempotency_key: crypto.randomUUID() });
        setGeoStatus({ ok: true, text: 'Check-in verified successfully.' });
      } else {
        await apiClient.checkOut(id, payload);
        setGeoStatus({ ok: true, text: 'Check-out verified. Visit completed.' });
      }
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
              {customer?.name || `Customer #${visit.customer_id.substring(0, 8)}`}
            </h1>
            {customer?.address && (
              <p className="font-caption text-xs text-on-surface-variant mt-1">{customer.address}</p>
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
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">
              Check-Out
            </p>
            <p className="font-body-md text-sm text-on-surface font-medium">
              {visit.check_out_at ? new Date(visit.check_out_at).toLocaleString() : 'Not checked out'}
            </p>
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
                <Input
                  label="LATITUDE"
                  type="number"
                  step="any"
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                  placeholder="—"
                />
                <Input
                  label="LONGITUDE"
                  type="number"
                  step="any"
                  value={lng}
                  onChange={(e) => setLng(e.target.value)}
                  placeholder="—"
                />
                <Input
                  label="ACCURACY (M)"
                  type="number"
                  step="any"
                  value={accuracy}
                  onChange={(e) => setAccuracy(e.target.value)}
                />
              </div>

              {canCheckIn && (
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  className="w-full"
                  isLoading={isSubmittingGeo}
                  disabled={!lat || !lng}
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
                  disabled={!lat || !lng}
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

        {/* Media */}
        <Card variant="default" className="space-y-space-4">
          <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
            <ImageIcon className="w-5 h-5 text-primary" />
            <h3 className="font-headline-sm text-base font-bold text-primary">
              Attached Media &amp; Files ({mediaList.length})
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

          {mediaList.length === 0 ? (
            <p className="font-caption text-xs text-on-surface-variant py-space-4 text-center">
              No media attachments uploaded for this visit.
            </p>
          ) : (
            <div className="space-y-space-3 max-h-72 overflow-y-auto pr-space-1">
              {mediaList.map((media) => (
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
      </div>
    </div>
  );
};
