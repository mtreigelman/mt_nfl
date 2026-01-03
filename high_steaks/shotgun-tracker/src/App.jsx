import React, { useState, useEffect } from 'react';
import { AlertCircle, Home, ChevronDown } from 'lucide-react';

const LEAGUE_CONFIG = {
  '2024': '1117575265233842176',
  '2025': '1236543313314586624'
};

const ShotgunTracker = () => {
  const [view, setView] = useState('home'); // 'home', 'season', 'week', 'user'
  const [selectedSeason, setSelectedSeason] = useState('all');
  const [selectedWeek, setSelectedWeek] = useState('all');
  const [selectedUser, setSelectedUser] = useState(null);
  const [nflState, setNflState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [shotgunData, setShotgunData] = useState({});
  const [owners, setOwners] = useState([]);
  const [ownerAvatars, setOwnerAvatars] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchAllData();
  }, []);

  useEffect(() => {
    // Determine view based on selections
    if (selectedSeason === 'all' && selectedWeek === 'all') {
      setView('home');
    } else if (selectedUser) {
      setView('user');
    } else if (selectedWeek !== 'all') {
      setView('week');
    } else if (selectedSeason !== 'all') {
      setView('season');
    }
  }, [selectedSeason, selectedWeek, selectedUser]);

  const fetchAllData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      console.log('Starting data fetch...');
      const stateRes = await fetch('https://api.sleeper.app/v1/state/nfl');
      const state = await stateRes.json();
      setNflState(state);
      console.log('NFL State:', state);

      console.log('Fetching players...');
      const playersRes = await fetch('https://api.sleeper.app/v1/players/nfl');
      const players = await playersRes.json();
      console.log('Players loaded:', Object.keys(players).length);

      const allShotguns = {};
      const ownerSet = new Set();
      const avatarMap = {};

      for (const [year, leagueId] of Object.entries(LEAGUE_CONFIG)) {
        console.log(`Fetching ${year} season...`);
        const seasonData = await fetchSeasonData(leagueId, year, players);
        allShotguns[year] = seasonData.shotguns;
        seasonData.owners.forEach(owner => ownerSet.add(owner));
        Object.assign(avatarMap, seasonData.avatars);
        console.log(`${year} data:`, seasonData);
      }

      console.log('All shotguns:', allShotguns);
      console.log('All owners:', Array.from(ownerSet));
      
      setShotgunData(allShotguns);
      setOwners(Array.from(ownerSet).sort());
      setOwnerAvatars(avatarMap);
    } catch (err) {
      console.error('Error:', err);
      setError(`Failed to load data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchSeasonData = async (leagueId, year, players) => {
    const usersRes = await fetch(`https://api.sleeper.app/v1/league/${leagueId}/users`);
    const users = await usersRes.json();
    
    const rostersRes = await fetch(`https://api.sleeper.app/v1/league/${leagueId}/rosters`);
    const rosters = await rostersRes.json();

    const userMap = {};
    const avatarMap = {};
    users.forEach(user => {
      const roster = rosters.find(r => r.owner_id === user.user_id);
      if (roster) {
        userMap[roster.roster_id] = user.display_name;
        avatarMap[user.display_name] = user.avatar ? `https://sleepercdn.com/avatars/thumbs/${user.avatar}` : null;
      }
    });

    const shotguns = {};
    const maxWeek = 14;

    for (let week = 1; week <= maxWeek; week++) {
      try {
        const matchupsRes = await fetch(`https://api.sleeper.app/v1/league/${leagueId}/matchups/${week}`);
        if (!matchupsRes.ok) continue;
        const matchups = await matchupsRes.json();
        if (!matchups || matchups.length === 0) continue;

        matchups.forEach(matchup => {
          const ownerName = userMap[matchup.roster_id];
          if (!ownerName) return;

          const opponent = matchups.find(m => m.matchup_id === matchup.matchup_id && m.roster_id !== matchup.roster_id);
          const opponentName = opponent ? userMap[opponent.roster_id] : 'Unknown';

          if (matchup.starters && matchup.players_points) {
            matchup.starters.forEach(playerId => {
              const points = matchup.players_points[playerId] || 0;
              if (points <= 0) {
                const playerInfo = players[playerId];
                const playerName = playerInfo 
                  ? `${playerInfo.first_name} ${playerInfo.last_name}`.trim() || playerId
                  : playerId;
                const position = playerInfo?.position || 'N/A';
                
                if (!shotguns[ownerName]) {
                  shotguns[ownerName] = [];
                }
                shotguns[ownerName].push({
                  playerId,
                  playerName,
                  position,
                  week,
                  year,
                  points,
                  opponent: opponentName
                });
              }
            });
          }
        });
      } catch (err) {
        console.error(`Error fetching week ${week}:`, err);
      }
    }

    return { shotguns, owners: Object.values(userMap), avatars: avatarMap };
  };

  const getOwnerShotguns = (ownerName, season = null, week = null) => {
    let shotguns = [];
    
    if (season && season !== 'all') {
      shotguns = shotgunData[season]?.[ownerName] || [];
    } else {
      Object.entries(shotgunData).forEach(([year, seasonShots]) => {
        if (seasonShots[ownerName]) {
          shotguns.push(...seasonShots[ownerName]);
        }
      });
    }

    if (week && week !== 'all') {
      shotguns = shotguns.filter(s => s.week === parseInt(week));
    }

    return shotguns;
  };

  const getShotgunCount = (ownerName, season = null, week = null) => {
    return getOwnerShotguns(ownerName, season, week).length;
  };

  const handleHomeClick = () => {
    setSelectedSeason('all');
    setSelectedWeek('all');
    setSelectedUser(null);
    setView('home');
  };

  const handleSeasonChange = (season) => {
    setSelectedSeason(season);
    setSelectedWeek('all');
    setSelectedUser(null);
  };

  const handleWeekChange = (week) => {
    setSelectedWeek(week);
    setSelectedUser(null);
  };

  const handleUserClick = (userName) => {
    setSelectedUser(userName);
    setView('user');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gradient-to-br from-stone-900 via-amber-950 to-stone-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-600 mx-auto mb-4"></div>
          <p className="text-amber-200">Grilling up the data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-gradient-to-br from-stone-900 via-amber-950 to-stone-900">
        <div className="text-center max-w-lg">
          <AlertCircle className="w-12 h-12 text-red-600 mx-auto mb-4" />
          <p className="text-xl mb-2 text-white">{error}</p>
          <button onClick={fetchAllData} className="bg-red-800 hover:bg-red-700 px-6 py-2 rounded-lg font-bold text-white transition">
            Try Again
          </button>
        </div>
      </div>
    );
  }

  const currentShotguns = owners.map(owner => ({
    name: owner,
    shotguns: getOwnerShotguns(owner, selectedSeason === 'all' ? null : selectedSeason, selectedWeek === 'all' ? null : selectedWeek),
    count: getShotgunCount(owner, selectedSeason === 'all' ? null : selectedSeason, selectedWeek === 'all' ? null : selectedWeek)
  })).sort((a, b) => b.count - a.count);

  console.log('Current view:', view);
  console.log('Selected season:', selectedSeason);
  console.log('Selected week:', selectedWeek);
  console.log('Owners:', owners);
  console.log('Current shotguns:', currentShotguns);

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-900 via-amber-950 to-stone-900">
      {/* Header */}
      <div className="bg-gradient-to-r from-red-900 via-red-800 to-amber-900 p-6 border-b-4 border-amber-600 shadow-2xl">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-4xl font-bold text-amber-100 tracking-wide" style={{textShadow: '2px 2px 4px rgba(0,0,0,0.5)'}}>
                🥩 HIGH STEAKS 🥩
              </h1>
              <h2 className="text-2xl font-semibold text-amber-200">Fantasy Football Shotgun Tracker</h2>
              {nflState && (
                <p className="text-sm text-amber-300 font-medium mt-1">
                  📅 {nflState.season} Season • Week {nflState.week}
                </p>
              )}
            </div>
            <button
              onClick={handleHomeClick}
              className="flex items-center gap-2 bg-amber-800 hover:bg-amber-700 px-4 py-2 rounded-lg font-bold text-white transition"
            >
              <Home size={20} />
              All Time
            </button>
          </div>

          {/* Navigation */}
          <div className="flex gap-4 mt-4">
            <div className="relative">
              <select
                value={selectedSeason}
                onChange={(e) => handleSeasonChange(e.target.value)}
                className="appearance-none bg-stone-800 text-amber-100 px-4 py-2 pr-10 rounded-lg border-2 border-amber-900 hover:border-amber-700 focus:outline-none focus:border-amber-600 cursor-pointer font-medium"
              >
                <option value="all">All Seasons</option>
                {Object.keys(LEAGUE_CONFIG).sort().reverse().map(year => (
                  <option key={year} value={year}>{year} Season</option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-amber-400" size={20} />
            </div>

            <div className="relative">
              <select
                value={selectedWeek}
                onChange={(e) => handleWeekChange(e.target.value)}
                disabled={selectedSeason === 'all'}
                className={`appearance-none bg-stone-800 text-amber-100 px-4 py-2 pr-10 rounded-lg border-2 border-amber-900 hover:border-amber-700 focus:outline-none focus:border-amber-600 font-medium ${
                  selectedSeason === 'all' ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
                }`}
              >
                <option value="all">Whole Season</option>
                {[...Array(14)].map((_, i) => (
                  <option key={i + 1} value={i + 1}>Week {i + 1}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-amber-400" size={20} />
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-6xl mx-auto p-8">
        {/* Debug Info */}
        {owners.length === 0 && (
          <div className="bg-yellow-900 border-2 border-yellow-600 rounded-lg p-4 mb-6 text-yellow-100">
            <p className="font-bold">⚠️ No data loaded. Check console for errors.</p>
            <p className="text-sm mt-2">Owners: {owners.length} | Shotgun Data: {Object.keys(shotgunData).length} seasons</p>
          </div>
        )}
        
        {/* Home View - Just Counts */}
        {view === 'home' && (
          <div>
            <h3 className="text-3xl font-bold mb-6 text-amber-400 text-center">🏆 All-Time Shotgun Totals</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {currentShotguns.map(({ name, count }) => (
                <button
                  key={name}
                  onClick={() => handleUserClick(name)}
                  className="bg-gradient-to-r from-stone-800 to-stone-900 p-6 rounded-lg border-2 border-amber-900 hover:border-red-600 transition shadow-lg hover:shadow-2xl cursor-pointer"
                >
                  <div className="flex items-center gap-4">
                    {ownerAvatars[name] ? (
                      <img src={ownerAvatars[name]} alt={name} className="w-16 h-16 rounded-full border-2 border-amber-600" />
                    ) : (
                      <div className="w-16 h-16 rounded-full bg-amber-800 flex items-center justify-center text-2xl font-bold border-2 border-amber-600 text-white">
                        {name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div className="flex-1 text-left">
                      <h4 className="text-xl font-bold text-amber-100">{name}</h4>
                      <div className="flex items-center gap-2 mt-1">
                        {count === 0 ? (
                          <span className="text-green-500 font-bold">✅ RELOAD NEEDED!</span>
                        ) : (
                          <>
                            <span className="text-red-500 font-black text-2xl">{count}</span>
                            <span className="text-2xl">🔫</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Season/Week View - Detailed */}
        {(view === 'season' || view === 'week') && (
          <div>
            <h3 className="text-3xl font-bold mb-6 text-amber-400 text-center">
              {selectedWeek !== 'all' ? `🔥 ${selectedSeason} Season - Week ${selectedWeek}` : `🔥 ${selectedSeason} Season`}
            </h3>
            <div className="space-y-4">
              {currentShotguns.filter(o => o.count > 0).map(({ name, shotguns, count }) => (
                <div key={name} className="bg-gradient-to-r from-stone-800 to-stone-900 p-5 rounded-lg border-2 border-amber-900 hover:border-red-600 transition shadow-lg">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      {ownerAvatars[name] ? (
                        <img src={ownerAvatars[name]} alt={name} className="w-12 h-12 rounded-full border-2 border-amber-600" />
                      ) : (
                        <div className="w-12 h-12 rounded-full bg-amber-800 flex items-center justify-center text-xl font-bold border-2 border-amber-600 text-white">
                          {name.charAt(0).toUpperCase()}
                        </div>
                      )}
                      <h4 className="text-2xl font-bold text-amber-100">{name}</h4>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-red-500 font-black text-3xl">{count}</span>
                      <span className="text-4xl">🔫</span>
                    </div>
                  </div>
                  <div className="grid gap-2 ml-16">
                    {shotguns.map((shot, idx) => (
                      <div key={idx} className="bg-stone-900 p-3 rounded border-l-4 border-red-700 text-amber-200">
                        <div className="flex justify-between items-center">
                          <div>
                            <span className="font-semibold text-amber-400">{shot.playerName}</span>
                            <span className="text-gray-400 text-sm ml-2">({shot.position})</span>
                          </div>
                          <span className="text-sm text-gray-400">
                            Week {shot.week} • {shot.points} pts • vs {shot.opponent}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* User Detail View */}
        {view === 'user' && selectedUser && (
          <div>
            <div className="flex items-center justify-center gap-4 mb-6">
              {ownerAvatars[selectedUser] ? (
                <img src={ownerAvatars[selectedUser]} alt={selectedUser} className="w-20 h-20 rounded-full border-4 border-amber-600" />
              ) : (
                <div className="w-20 h-20 rounded-full bg-amber-800 flex items-center justify-center text-3xl font-bold border-4 border-amber-600 text-white">
                  {selectedUser.charAt(0).toUpperCase()}
                </div>
              )}
              <h3 className="text-4xl font-bold text-amber-400">{selectedUser}'s Complete History</h3>
            </div>
            
            <div className="bg-gradient-to-r from-stone-800 to-stone-900 p-6 rounded-lg border-2 border-amber-900 shadow-lg">
              <div className="flex items-center justify-between mb-6 pb-4 border-b-2 border-amber-800">
                <h4 className="text-2xl font-bold text-amber-100">Total Shotguns</h4>
                <div className="flex items-center gap-3">
                  <span className="text-red-500 font-black text-4xl">{getShotgunCount(selectedUser)}</span>
                  <span className="text-5xl">🔫</span>
                </div>
              </div>
              
              <div className="space-y-3">
                {getOwnerShotguns(selectedUser).map((shot, idx) => (
                  <div key={idx} className="bg-stone-900 p-4 rounded border-l-4 border-red-700 text-amber-200">
                    <div className="flex justify-between items-center">
                      <div>
                        <span className="font-bold text-amber-400 text-lg">{shot.playerName}</span>
                        <span className="text-gray-400 text-sm ml-2">({shot.position})</span>
                      </div>
                      <div className="text-right text-sm text-gray-400">
                        <div>{shot.year} Season • Week {shot.week}</div>
                        <div>{shot.points} pts • vs {shot.opponent}</div>
                      </div>
                    </div>
                  </div>
                ))}
                {getOwnerShotguns(selectedUser).length === 0 && (
                  <div className="text-center py-8 text-green-400 text-xl font-bold">
                    ✅ RELOAD NEEDED! No shotguns owed!
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ShotgunTracker;