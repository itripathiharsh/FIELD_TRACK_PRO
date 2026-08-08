import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, Image as ImageIcon, MapPin, Upload, Download } from 'lucide-react';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { apiClient } from '../api/client';
import { Visit, GeoVerificationLog, VisitMedia } from '../types';
import { ENV } from '../config/env';

export const VisitDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [visit, setVisit] = useState<Visit | null>(null);
  const [geoLogs, setGeoLogs] = useState<GeoVerificationLog[]>([]);
  const [mediaList, setMediaList] = useState<VisitMedia[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Geo Check-In state
  const [checkInLat, setCheckInLat] = useState('12.9716');
  const [checkInLng, setCheckInLng] = useState('77.5946');
  const [checkInAccuracy, setCheckInAccuracy] = useState('10');
  const [checkInStatus, setCheckInStatus] = useState<string | null>(null);
  const [isCheckingIn, setIsCheckingIn] = useState(false);

  // Media upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const reloadData = () => {
    if (!id) return;
    Promise.all([
      apiClient.getVisitById(id),
      apiClient.getVisitGeoLogs(id).catch(() => []),
      apiClient.getVisitMedia(id).catch(() => []),
    ])
      .then(([vData, gData, mData]) => {
        setVisit(vData);
        setGeoLogs(gData);
        setMediaList(mData);
      })
      .catch((err) => setError(err.message || 'Failed to load visit details'));
  };

  useEffect(() => {
    if (!id) return;
    setIsLoading(true);
    reloadData();
    setIsLoading(false);
  }, [id]);

  const handlePerformCheckIn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    setCheckInStatus(null);
    setIsCheckingIn(true);
    try {
      await apiClient.checkIn(id, {
        latitude: parseFloat(checkInLat),
        longitude: parseFloat(checkInLng),
        accuracy_m: parseFloat(checkInAccuracy),
        is_mock_location: false,
      });
      setCheckInStatus('Check-in verified successfully!');
      reloadData();
    } catch (err: any) {
      setCheckInStatus(`Check-in failed: ${err.message || 'Verification rejected'}`);
    } finally {
      setIsCheckingIn(false);
    }
  };

  const handleUploadMedia = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !selectedFile) return;
    setUploadStatus(null);
    setIsUploading(true);
    try {
      await apiClient.uploadMedia(id, selectedFile);
      setUploadStatus('Media photo uploaded successfully!');
      setSelectedFile(null);
      reloadData();
    } catch (err: any) {
      setUploadStatus(`Upload failed: ${err.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  if (isLoading) {
    return <div className="py-space-12 text-center text-on-surface-variant font-caption">Loading visit telemetry details...</div>;
  }

  if (error || !visit) {
    return (
      <div className="space-y-space-4 font-body-md text-on-surface">
        <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate('/visits')}>
          Back to Visits Schedule
        </Button>
        <div className="p-space-6 bg-error-container border border-error rounded-xl text-on-error-container font-body-md">
          {error || 'Visit record not found'}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate('/visits')}>
        Back to Visits Schedule
      </Button>

      {/* Header Info Card */}
      <Card variant="default">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-4 border-b border-surface-container-highest pb-space-4 mb-space-4">
          <div>
            <span className="font-caption text-xs text-on-surface-variant uppercase tracking-wider block mb-1">
              VISIT RECORD #{visit.id}
            </span>
            <h1 className="font-headline-lg text-2xl font-bold text-primary">
              {visit.customer_name || `Customer #${visit.customer_id}`}
            </h1>
            <p className="font-caption text-xs text-on-surface-variant mt-1">{visit.purpose || 'Field Site Visit'}</p>
          </div>
          <StatusBadge status={visit.status} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-4 text-body-md">
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">Scheduled Start / End</p>
            <p className="font-body-md text-sm text-on-surface font-medium">
              {visit.scheduled_start_time
                ? new Date(visit.scheduled_start_time).toLocaleString()
                : (visit as any).scheduled_at
                ? new Date((visit as any).scheduled_at).toLocaleString()
                : 'N/A'}
            </p>
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">Actual Check-In</p>
            <p className="font-body-md text-sm text-on-surface font-medium">
              {visit.actual_check_in_time || (visit as any).check_in_at
                ? new Date(visit.actual_check_in_time || (visit as any).check_in_at).toLocaleString()
                : 'Not Checked In'}
            </p>
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">Verification Failures</p>
            <p className={`font-headline-sm text-sm ${visit.verification_failure_count > 0 ? 'text-secondary font-bold bg-secondary-fixed/40 px-2 py-0.5 rounded inline-block' : 'text-primary font-bold'}`}>
              {visit.verification_failure_count || 0} attempt(s)
            </p>
          </div>
        </div>
      </Card>

      {/* Grid: Geo Verification Logs & Media Attachments */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-6">
        {/* Geo Verification & Check-In Card */}
        <Card variant="default" className="space-y-space-4">
          <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
            <ShieldCheck className="w-5 h-5 text-primary" />
            <h3 className="font-headline-sm text-base font-bold text-primary">GPS Verification & Check-In ({geoLogs.length})</h3>
          </div>

          {/* Interactive Check-in Form */}
          <form onSubmit={handlePerformCheckIn} className="p-space-4 bg-surface-container-low border border-outline-variant rounded-xl space-y-space-3">
            <p className="font-headline-sm text-sm text-primary font-bold flex items-center gap-space-1.5">
              <MapPin className="w-4 h-4 text-secondary-container" /> Execute Geo Check-In
            </p>
            {checkInStatus && (
              <div className={`p-space-2.5 rounded-lg border font-body-md text-xs ${checkInStatus.includes('failed') ? 'bg-error-container text-on-error-container border-error' : 'bg-primary-container text-on-primary-container border-primary-container'}`}>
                {checkInStatus}
              </div>
            )}
            <div className="grid grid-cols-3 gap-space-2">
              <Input
                label="LATITUDE"
                type="number"
                step="any"
                value={checkInLat}
                onChange={(e) => setCheckInLat(e.target.value)}
              />
              <Input
                label="LONGITUDE"
                type="number"
                step="any"
                value={checkInLng}
                onChange={(e) => setCheckInLng(e.target.value)}
              />
              <Input
                label="ACCURACY (M)"
                type="number"
                step="any"
                value={checkInAccuracy}
                onChange={(e) => setCheckInAccuracy(e.target.value)}
              />
            </div>
            <Button
              type="submit"
              variant="secondary"
              size="md"
              className="w-full"
              isLoading={isCheckingIn}
            >
              {isCheckingIn ? 'Verifying GPS...' : 'Perform Check-In'}
            </Button>
          </form>

          {/* Geo Logs Audit List */}
          {geoLogs.length === 0 ? (
            <p className="font-caption text-xs text-on-surface-variant py-space-4 text-center">No geo check attempts recorded for this visit.</p>
          ) : (
            <div className="space-y-space-3 max-h-64 overflow-y-auto pr-space-1">
              {geoLogs.map((log) => (
                <div key={log.id} className="p-space-3 bg-surface-container-low border border-outline-variant rounded-lg font-body-md text-xs space-y-space-1">
                  <div className="flex items-center justify-between">
                    <span className="font-headline-sm text-primary font-bold">{log.verification_type}</span>
                    <StatusBadge status={log.is_valid ? 'VALID' : 'INVALID'} size="sm" />
                  </div>
                  <p className="font-caption text-on-surface-variant font-mono">
                    Coords: {log.latitude}, {log.longitude}
                  </p>
                  {log.distance_from_target_m !== null && (
                    <p className="font-caption text-on-surface-variant">Distance to target: {Math.round(log.distance_from_target_m)}m</p>
                  )}
                  {log.failure_reason && <p className="text-error font-semibold">Reason: {log.failure_reason}</p>}
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Media Attachments & Upload Card */}
        <Card variant="default" className="space-y-space-4">
          <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
            <ImageIcon className="w-5 h-5 text-primary" />
            <h3 className="font-headline-sm text-base font-bold text-primary">Attached Media & Files ({mediaList.length})</h3>
          </div>

          {/* Interactive File Upload Form */}
          <form onSubmit={handleUploadMedia} className="p-space-4 bg-surface-container-low border border-outline-variant rounded-xl space-y-space-3">
            <p className="font-headline-sm text-sm text-primary font-bold flex items-center gap-space-1.5">
              <Upload className="w-4 h-4 text-secondary-container" /> Upload Visit Attachment
            </p>
            {uploadStatus && (
              <div className={`p-space-2.5 rounded-lg border font-body-md text-xs ${uploadStatus.includes('failed') ? 'bg-error-container text-on-error-container border-error' : 'bg-primary-container text-on-primary-container border-primary-container'}`}>
                {uploadStatus}
              </div>
            )}
            <input
              type="file"
              onChange={(e) => setSelectedFile(e.target.files ? e.target.files[0] : null)}
              className="w-full bg-surface border border-outline-variant rounded-lg px-space-3 py-space-2 text-on-surface font-body-md text-xs file:bg-surface-container file:text-on-surface file:border-0 file:rounded file:px-space-2 file:py-space-1 file:mr-space-2 cursor-pointer"
            />
            <Button
              type="submit"
              variant="secondary"
              size="md"
              className="w-full"
              disabled={!selectedFile}
              isLoading={isUploading}
            >
              {isUploading ? 'Uploading Image...' : 'Upload Attachment'}
            </Button>
          </form>

          {/* Media Attachments List */}
          {mediaList.length === 0 ? (
            <p className="font-caption text-xs text-on-surface-variant py-space-4 text-center">No media attachments uploaded for this visit.</p>
          ) : (
            <div className="space-y-space-3 max-h-64 overflow-y-auto pr-space-1">
              {mediaList.map((media) => (
                <div key={media.id} className="p-space-3 bg-surface-container-low border border-outline-variant rounded-lg font-body-md text-xs flex items-center justify-between">
                  <div>
                    <p className="font-headline-sm text-primary font-bold">{media.storage_key.split('/').pop()}</p>
                    <p className="font-caption text-on-surface-variant">Size: {media.file_size_bytes} bytes | Type: {media.media_type}</p>
                  </div>
                  <a
                    href={`${ENV.API_BASE_URL}/api/v1/media/${media.id}/download`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Button variant="outline" size="sm" icon={Download}>
                      Download
                    </Button>
                  </a>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
